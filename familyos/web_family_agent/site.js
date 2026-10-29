'use strict';

const chats = {
  personal: {
    name: 'Your FamilyOS',
    html: '<div class="day">Today · 8:42 AM</div>'
      + '<div class="bubble mine">Can everyone do dinner together this weekend?</div>'
      + '<div class="thinking"><i></i><i></i><i></i><span>Checking shared calendars</span></div>'
      + '<div class="agent-card"><span class="card-label">FamilyOS found a time</span><h3>Saturday · 7:00 PM</h3><p>Everyone is free. The Oak &amp; Olive has a table for four.</p><div class="people"><b>A</b><b>P</b><b>M</b><b>V</b></div><div class="card-actions"><button>Change</button><button class="yes">Prepare invite</button></div></div>'
      + '<div class="bubble theirs">Ready when you are. I won’t send it until you approve.</div>',
  },
  family: {
    name: 'Iyer family + FamilyOS',
    html: '<div class="day">Family chat · Today</div>'
      + '<div class="bubble other"><b>Priya</b>Can we do a movie night Friday?</div>'
      + '<div class="bubble other second"><b>Meera</b>Yes! But not too late 🍿</div>'
      + '<div class="agent-card poll"><span class="card-label">FamilyOS · quick vote</span><h3>Pick Friday’s movie</h3><button>Inside Out 2 <b>A · P · M</b></button><button>Moana 2 <b>V</b></button><button>Something else <b>＋</b></button></div>'
      + '<div class="bubble theirs">I’ll close the vote tomorrow at 6. Nothing booked.</div>',
  },
};

document.querySelectorAll('[data-mode]').forEach((button) => {
  button.addEventListener('click', () => {
    const mode = button.dataset.mode;
    document.querySelectorAll('[data-mode]').forEach((item) => item.classList.toggle('active', item === button));
    document.querySelector('[data-chat-name]').textContent = chats[mode].name;
    const chat = document.querySelector('[data-chat]');
    chat.classList.add('changing');
    window.setTimeout(() => { chat.innerHTML = chats[mode].html; chat.classList.remove('changing'); }, 140);
  });
});

document.querySelectorAll('[data-scroll]').forEach((button) => {
  button.addEventListener('click', () => document.getElementById(button.dataset.scroll)?.scrollIntoView({ behavior: 'smooth' }));
});
