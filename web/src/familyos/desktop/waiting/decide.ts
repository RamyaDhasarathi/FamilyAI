// Accept / ✕ for a proposal, shared by Waiting on you, the Inbox (rows, Dates
// spotted, the notice drawer) and Ask's action cards (MASTER_AGENT.md §7
// Phase 3, §3.3 "Proposals, not actions"). Each runs only from a click; the
// store moves an accepted proposal to its agent (calendar / reminder → the
// calendar, task / payment / errand → the to-dos) and writes the audit row.
// The app toast offers Undo, which writes its own audit row.
import { useDesk } from '../../desk/store';
import { useFamilyOS } from '../../store/useFamilyOS';
import { fmtText } from '../../desk/format';
import { useDeskUI } from '../shell/useDeskUI';

const UNDO_MS = 6000;

/** Where an accepted proposal went, for the toast and the action cards. */
export function placeOf(proposalId: string): string {
  const s = useDesk.getState();
  const p = s.proposals.find((x) => x.id === proposalId);
  if (!p) return '';
  if (p.lastDecision?.moved) return 'Moved on the calendar.';
  if (p.lastDecision?.createdTodoId) return 'On your to-dos now.';
  return 'On the calendar now.';
}

function undoToast(id: string, text: string) {
  useFamilyOS.getState().toast(text, {
    duration: UNDO_MS,
    action: {
      label: 'Undo',
      onPress: () => {
        if (useDesk.getState().undoProposal(id)) useFamilyOS.getState().toast('Undone. Nothing else changed.');
      },
    },
  });
}

/** Accept after a click: toast with Undo, and the new to-do / calendar row glows. */
export function acceptWithUndo(id: string): boolean {
  const desk = useDesk.getState();
  if (!desk.acceptProposal(id)) return false;
  const p = useDesk.getState().proposals.find((x) => x.id === id);
  const made = p?.lastDecision?.createdTodoId ?? p?.lastDecision?.createdAgendaId ?? p?.lastDecision?.moved?.agendaId;
  if (made) useDeskUI.getState().flashIds([made]);
  const title = p ? fmtText(p.title, useDesk.getState().settings.currency) : 'it';
  undoToast(id, `Accepted “${title}”. ${placeOf(id)}`);
  return true;
}

/** ✕ after a click: nothing is created; the toast offers Undo. */
export function dismissWithUndo(id: string): boolean {
  const desk = useDesk.getState();
  const p = desk.proposals.find((x) => x.id === id);
  if (!desk.dismissProposal(id)) return false;
  const title = p ? fmtText(p.title, desk.settings.currency) : 'it';
  undoToast(id, `Dismissed “${title}”. Nothing else changed.`);
  return true;
}
