"""Purchase Agent implementation for Family OS."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.core.exceptions import PermissionDenied
from app.db.models.conversation import (
    AgentType,
    ContentType,
    Conversation,
    Message,
    SenderType,
)
from app.db.models.family import FamilyMembership
from app.db.models.purchase import (
    ApprovalState,
    ExecutionState,
    ProductCandidate,
    PurchaseTask,
    PurchaseTaskStatus,
    SourceType,
)
from app.policies.engine import PolicyEngine
from app.policies.rules import RA
from app.providers.llm.base import ChatMessage
from app.providers.llm.factory import get_llm_provider
from app.providers.products.factory import get_product_provider
from app.services.audit_service import AuditService

_engine = PolicyEngine()
_auditor = AuditService()


class PurchaseAgent(BaseAgent):
    """Conversational shopping assistant that finds, compares, and prepares purchases."""

    @property
    def agent_type(self) -> str:
        return "PURCHASE"

    async def process_message(
        self,
        db: AsyncSession,
        conversation_id: Optional[str],
        user_message: str,
        task_id: Optional[str],
        membership: FamilyMembership,
        correlation_id: str = "chat",
    ) -> Dict[str, Any]:
        """Main chat entry point for the Purchase Agent."""
        # 1. Evaluate FGP permission to use Purchase Agent
        decision = await _engine.evaluate(
            db=db,
            principal_membership_id=membership.id,
            family_id=membership.family_id,
            resource=RA.AGENT_PURCHASE_USE[0],
            action=RA.AGENT_PURCHASE_USE[1],
            purpose="Use Purchase Agent",
        )
        if decision.effect == "DENY":
            raise PermissionDenied(decision.human_readable_reason)

        # 2. Get or create conversation
        if not conversation_id:
            conv_id = str(uuid.uuid4())
            conv = Conversation(
                id=conv_id,
                family_id=membership.family_id,
                owner_membership_id=membership.id,
                agent_type=AgentType.PURCHASE,
            )
            db.add(conv)
            conversation_id = conv_id
        else:
            conv_res = await db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.family_id == membership.family_id,
                )
            )
            conv = conv_res.scalar_one_or_none()
            if not conv:
                conv_id = str(uuid.uuid4())
                conv = Conversation(
                    id=conv_id,
                    family_id=membership.family_id,
                    owner_membership_id=membership.id,
                    agent_type=AgentType.PURCHASE,
                )
                db.add(conv)
                conversation_id = conv_id

        # 3. Save User message
        user_msg_id = str(uuid.uuid4())
        user_msg = Message(
            id=user_msg_id,
            conversation_id=conversation_id,
            sender_type=SenderType.USER,
            content=user_message,
            content_type=ContentType.TEXT,
        )
        db.add(user_msg)
        await db.flush()

        # 4. Get or create PurchaseTask
        task: Optional[PurchaseTask] = None
        user_msg_lower = user_message.lower()
        is_new_search = any(w in user_msg_lower for w in ["find", "search", "buy", "get me", "look for", "looking for", "i want", "i need"])

        if task_id:
            task_res = await db.execute(
                select(PurchaseTask).where(
                    PurchaseTask.id == task_id,
                    PurchaseTask.family_id == membership.family_id,
                )
            )
            existing_task = task_res.scalar_one_or_none()
            if existing_task:
                # If existing task is finished or user is asking for a new item, start a fresh task
                if existing_task.status in (
                    PurchaseTaskStatus.COMPLETED,
                    PurchaseTaskStatus.FAILED,
                    PurchaseTaskStatus.CANCELLED,
                ) or is_new_search:
                    task = None
                else:
                    task = existing_task

        if not task:
            task = PurchaseTask(
                id=str(uuid.uuid4()),
                family_id=membership.family_id,
                requester_membership_id=membership.id,
                conversation_id=conversation_id,
                original_request=user_message,
                status=PurchaseTaskStatus.RECEIVED,
                approval_state=ApprovalState.NOT_REQUIRED,
                execution_state=ExecutionState.NOT_STARTED,
            )
            db.add(task)
            await db.flush()

        # 5. Load recent conversation history
        hist_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        hist_res = await db.execute(hist_stmt)
        messages_history = list(reversed(hist_res.scalars().all()))

        # 6. Extract intent using LLM provider
        llm = get_llm_provider()
        prompt_messages: List[ChatMessage] = [
            ChatMessage(
                role="system",
                content=(
                    "You are the Family OS Purchase Agent. Understand the family member's request, "
                    "extract shopping intent, and immediately prepare to search the live marketplace. "
                    "Always respond in JSON with schema: {"
                    "'response_type': 'recommendation', "
                    "'reply_text': 'string', "
                    "'purchase_intent': {'category': 'string (e.g. HEADPHONES, MOUSE, LAPTOP, KEYBOARD, SMARTPHONE, etc.)', "
                    "'item': 'cleaned product search keywords', 'budget_amount': number or null, 'currency': 'INR', "
                    "'brand_preference': ['string'], 'required_specs': {}, 'missing_info': []}, "
                    "'ready_to_search': true, "
                    "'clarification_question': null}\n"
                    "RULES:\n"
                    "1. Whenever the user asks to find, buy, search, or look for ANY product, ALWAYS set ready_to_search to true.\n"
                    "2. Do NOT ask clarifying questions or stall. Extract whatever budget or keywords are given and search immediately."
                ),
            )
        ]
        for m in messages_history:
            role = "user" if m.sender_type == SenderType.USER else "assistant"
            prompt_messages.append(ChatMessage(role=role, content=m.content))

        llm_response = await llm.chat(prompt_messages)
        parsed_data = self._parse_llm_json(llm_response.content, user_message)

        reply_text = parsed_data.get("reply_text", "I'm looking into your request.")
        intent = parsed_data.get("purchase_intent", {})
        ready_to_search = parsed_data.get("ready_to_search", True)
        clarification_question = parsed_data.get("clarification_question")

        category = intent.get("category", "").upper()
        budget_amount = intent.get("budget_amount")
        brands = intent.get("brand_preference", [])

        # Update task intent
        task.parsed_intent_json = json.dumps(intent)
        if budget_amount:
            try:
                task.budget_amount = Decimal(str(budget_amount))
                task.currency = intent.get("currency", "INR")
            except Exception:
                pass

        candidates_out: List[Dict[str, Any]] = []
        is_dev_data = False

        # 7. Check if we should search or clarify
        # If user mentioned an item or asked to find/buy, ALWAYS trigger live search
        should_search = (
            ready_to_search
            or bool(intent.get("item"))
            or bool(category)
            or is_new_search
        )

        if clarification_question and not should_search:
            task.status = PurchaseTaskStatus.AWAITING_CLARIFICATION
            reply_text = clarification_question
        elif should_search:
            # Check catalogue search permission
            search_decision = await _engine.evaluate(
                db=db,
                principal_membership_id=membership.id,
                family_id=membership.family_id,
                resource=RA.PURCHASE_CATALOGUE_SEARCH[0],
                action=RA.PURCHASE_CATALOGUE_SEARCH[1],
                purpose="Search catalogue",
            )
            if search_decision.effect == "DENY":
                reply_text = "I cannot search the catalogue: " + search_decision.human_readable_reason
                task.status = PurchaseTaskStatus.FAILED
            else:
                task.status = PurchaseTaskStatus.SEARCHING
                product_provider = get_product_provider()
                results = await product_provider.search(
                    category=category,
                    query=user_message,
                    budget_amount=float(budget_amount) if budget_amount else None,
                    currency=intent.get("currency", "INR"),
                    brand_preference=brands,
                )

                task.status = PurchaseTaskStatus.COMPARING
                scored_candidates = []
                for r in results:
                    score = self._score_candidate(r, budget_amount, brands)
                    scored_candidates.append((score, r))

                # Sort descending by score and keep strictly top 3 candidates close to budget
                scored_candidates.sort(key=lambda x: x[0], reverse=True)
                scored_candidates = scored_candidates[:3]

                # Persist candidates
                for rank_idx, (score, r) in enumerate(scored_candidates, 1):
                    cand_id = str(uuid.uuid4())
                    cand_source = (
                        SourceType.REAL_PROVIDER
                        if getattr(r, "source_type", None) == "REAL_PROVIDER"
                        else SourceType.DEVELOPMENT_CATALOGUE
                    )
                    cand = ProductCandidate(
                        id=cand_id,
                        purchase_task_id=task.id,
                        provider=r.merchant or "Amazon India",
                        provider_product_id=r.provider_product_id,
                        title=r.title,
                        brand=r.brand,
                        price_amount=Decimal(str(r.price_amount)) if r.price_amount is not None else None,
                        currency=r.currency,
                        merchant=r.merchant,
                        product_url=r.product_url,
                        image_url=r.image_url,
                        availability=r.availability,
                        delivery_estimate=r.delivery_estimate,
                        warranty_details=r.warranty_details,
                        return_details=r.return_details,
                        specifications_json=json.dumps(r.specifications),
                        source_type=cand_source,
                    )
                    db.add(cand)
                    candidates_out.append({
                        "id": cand_id,
                        "title": r.title,
                        "brand": r.brand,
                        "price_amount": r.price_amount,
                        "currency": r.currency,
                        "merchant": r.merchant,
                        "product_url": r.product_url,
                        "image_url": r.image_url,
                        "availability": r.availability,
                        "delivery_estimate": r.delivery_estimate,
                        "warranty_details": r.warranty_details,
                        "return_details": r.return_details,
                        "specifications_json": r.specifications,
                        "source_type": cand_source.value,
                        "provider": r.merchant or "Amazon India",
                        "score": score,
                        "rank": rank_idx,
                    })

                is_dev_data = any(c.get("source_type") == "DEVELOPMENT_CATALOGUE" for c in candidates_out)
                task.status = PurchaseTaskStatus.RECOMMENDATION_READY
                if candidates_out:
                    top = candidates_out[0]
                    price_str = f"{top['currency']} {top['price_amount']}" if top.get("price_amount") else "Market Price"
                    if not is_dev_data:
                        reply_text = (
                            f"I tasked your Mobile-Use Agent to search Amazon live on your phone. "
                            f"I found the top {len(candidates_out)} products closest to your budget. "
                            f"Top recommendation: '{top['title'][:55]}' at {price_str}."
                        )
                    else:
                        reply_text = (
                            f"I found {len(candidates_out)} options from the catalogue. "
                            f"I recommend the {top['title']} priced at {price_str} based on your requirements."
                        )
                else:
                    reply_text = "I couldn't find any matching products in the marketplace for your criteria."
        else:
            task.status = PurchaseTaskStatus.UNDERSTANDING_REQUEST

        await db.flush()

        # 8. Save Agent message
        agent_msg_id = str(uuid.uuid4())
        agent_msg = Message(
            id=agent_msg_id,
            conversation_id=conversation_id,
            sender_type=SenderType.AGENT,
            content=reply_text,
            content_type=ContentType.STRUCTURED if candidates_out else ContentType.TEXT,
            metadata_json=json.dumps({
                "task_id": task.id,
                "task_status": task.status.value,
                "candidates_count": len(candidates_out),
                "is_development_data": is_dev_data,
            }),
        )
        db.add(agent_msg)
        await db.flush()

        available_actions = []
        if candidates_out:
            available_actions.extend(["select_candidate", "compare_candidates", "ask_question"])

        return {
            "conversation_id": conversation_id,
            "message_id": agent_msg_id,
            "agent_type": "PURCHASE",
            "reply": reply_text,
            "task_id": task.id,
            "task_status": task.status.value,
            "structured_response": {
                "parsed_intent": intent,
                "ready_to_search": ready_to_search,
                "recommendation_summary": reply_text,
            },
            "candidates": candidates_out,
            "available_actions": available_actions,
            "correlation_id": correlation_id,
            "is_development_data": is_dev_data,
        }

    def _parse_llm_json(self, content: str, user_message: str) -> Dict[str, Any]:
        """Safely extract JSON from model output or fallback deterministically."""
        try:
            # Look for JSON boundaries
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(content[start : end + 1])
                # Ensure ready_to_search is true if an item or category is identified
                intent = data.get("purchase_intent", {})
                if intent.get("item") or intent.get("category"):
                    data["ready_to_search"] = True
                return data
        except Exception:
            pass

        # Fallback keyword extraction for deterministic behavior
        msg_lower = user_message.lower()
        category = "ELECTRONICS"
        if "headphone" in msg_lower or "earphone" in msg_lower or "earbud" in msg_lower or "airpod" in msg_lower:
            category = "HEADPHONES"
        elif "mouse" in msg_lower:
            category = "MOUSE"
        elif "keyboard" in msg_lower:
            category = "KEYBOARD"
        elif "laptop" in msg_lower:
            category = "LAPTOP"
        elif "washing" in msg_lower or "machine" in msg_lower:
            category = "WASHING_MACHINE"
        elif "backpack" in msg_lower or "bag" in msg_lower:
            category = "BACKPACK"
        elif "phone" in msg_lower or "mobile" in msg_lower or "smartphone" in msg_lower:
            category = "SMARTPHONE"
        elif "watch" in msg_lower:
            category = "SMARTWATCH"
        elif "shoe" in msg_lower or "sneaker" in msg_lower:
            category = "FOOTWEAR"
        else:
            cleaned = re.sub(r"\b(find|search|buy|look for|get me|i need|i want|a|an|the|under|below|rs|inr)\b", "", msg_lower).strip()
            category = cleaned.split()[0].upper() if cleaned else "GENERAL"

        budget = None
        import re
        match = re.search(r"(?:under|below|for|budget)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*)", msg_lower)
        if match:
            budget = float(match.group(1).replace(",", ""))

        brands = []
        for b in ["bose", "sony", "boat", "jbl", "sennheiser", "logitech", "hp", "dell", "lenovo", "samsung", "apple", "lg", "whirlpool", "wildcraft"]:
            if b in msg_lower:
                brands.append(b.title())

        # Clean search query for item
        clean_item = re.sub(r"^(?:find|buy|search for|look for|get me|i want|i need)\s+", "", user_message, flags=re.IGNORECASE).strip()

        return {
            "response_type": "recommendation",
            "reply_text": f"Tasking Mobile-Use Agent to search live marketplace for {clean_item}.",
            "purchase_intent": {
                "category": category,
                "item": clean_item,
                "budget_amount": budget,
                "currency": "INR",
                "brand_preference": brands,
                "required_specs": {},
                "missing_info": [],
            },
            "ready_to_search": True,
            "clarification_question": None,
        }

    def _score_candidate(
        self,
        candidate,
        budget_amount: Optional[float],
        brand_preference: Optional[List[str]],
    ) -> float:
        """Deterministic candidate scoring: budget match (40), brand (20), availability (15), complete info (15), base (10)."""
        score = 10.0
        if budget_amount and candidate.price_amount is not None:
            if candidate.price_amount <= budget_amount:
                # Closer to the requested budget scores higher (up to 40)
                score += 40.0 - (budget_amount - candidate.price_amount) / budget_amount * 10.0
            else:
                score += max(0.0, 30.0 - (candidate.price_amount - budget_amount) / budget_amount * 20.0)

        if brand_preference and candidate.brand:
            if any(b.lower() == candidate.brand.lower() for b in brand_preference):
                score += 20.0

        if candidate.availability and "stock" in candidate.availability.lower():
            score += 15.0

        if candidate.warranty_details and candidate.delivery_estimate:
            score += 15.0

        return round(score, 1)
