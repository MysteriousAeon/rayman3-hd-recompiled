#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include "m6_test_input.h"
#include "g6p79_profile_handoff.h"
#include "g6p82_signin_notify.h"
#include <vector>
#undef NDEBUG
int main() {
  const char* path="m6_input_test_schedule.txt";
  { std::ofstream f(path); f << "100 40 1\n101 40 0\n200 44 1\n201 44 0\n300 26 1\n400 26 0\n"; }
  {
    m6input::Source src(path);
    assert(src.Sample(0).buttons == 0);
    auto query=src.Sample(150, false); assert(query.buttons == 0x10);
    auto press=src.Sample(150); assert(press.buttons == 0x10 && press.packet==query.packet);
    auto release=src.Sample(151); assert(release.buttons==0 && release.packet==press.packet+1);
    assert(src.Sample(250).buttons==0x1000); assert(src.Sample(251).buttons==0);
    auto move=src.Sample(350); assert(move.ly==32767);
    assert(src.Sample(399).packet==move.packet); assert(src.Sample(450).ly==0);
    { std::ofstream f(path, std::ios::app); f << "0 15 1"; }
    assert(src.Sample(500).buttons==0); // unfinished append must wait
    { std::ofstream f(path, std::ios::app); f << "\n0 15 0\n"; }
    assert(src.Sample(501).buttons==0x4000); assert(src.Sample(502).buttons==0);
    { std::ofstream f(path, std::ios::app); f << "0 300 -12000\n0 301 40000\n0 26 1\n0 44 2\n"; }
    auto analog=src.Sample(503); assert(analog.lx==-12000 && analog.ly==32767 && analog.buttons==0);
    { std::ofstream f(path, std::ios::app); f << "0 300 0\n0 301 0\n"; }
    auto digital=src.Sample(504); assert(digital.lx==0 && digital.ly==32767 && digital.packet==analog.packet+1);
  }
  // G6-P77: R3HD_TEST_INPUT_USER parsing and per-user routing (default = the M6 behaviour).
  assert(m6input::ParseTestUser(nullptr) == 0 && m6input::ParseTestUser("") == 0);
  assert(m6input::ParseTestUser("0") == 0 && m6input::ParseTestUser("1") == 1 && m6input::ParseTestUser("3") == 3);
  assert(m6input::ParseTestUser("4") == -1 && m6input::ParseTestUser("01") == -1 && m6input::ParseTestUser("x") == -1);
  assert(m6input::RouteFor(0, 0) == m6input::kSchedule);
  for (unsigned u = 1; u < 4; ++u) assert(m6input::RouteFor(u, 0) == m6input::kNotConnected);
  assert(m6input::RouteFor(0, 1) == m6input::kIdle && m6input::RouteFor(1, 1) == m6input::kSchedule);
  assert(m6input::RouteFor(2, 1) == m6input::kNotConnected && m6input::RouteFor(3, 1) == m6input::kNotConnected);
  assert(m6input::RouteFor(0, 3) == m6input::kIdle && m6input::RouteFor(3, 3) == m6input::kSchedule);
  for (unsigned u = 0; u < 4; ++u) assert(m6input::RouteFor(u, -1) == m6input::kNotConnected);
  // G6-P79: run-time route codes. Without codes the dynamic routing equals RouteFor(user, test_user).
  for (int t = -1; t < 4; ++t) {
    m6input::Routing r; r.schedule_user = t;
    for (unsigned u = 0; u < 4; ++u) assert(m6input::RouteFor(u, r) == m6input::RouteFor(u, t));
  }
  {
    m6input::Routing r;  // schedule on user 0
    assert(!m6input::ApplyRouteCode(r, 309, 1) && !m6input::ApplyRouteCode(r, 314, 1) && !m6input::ApplyRouteCode(r, 40, 1));
    assert(m6input::ApplyRouteCode(r, 311, 1));  // schedule -> user 1; user 0 idle
    assert(m6input::RouteFor(1, r) == m6input::kSchedule && m6input::RouteFor(0, r) == m6input::kIdle);
    assert(m6input::RouteFor(2, r) == m6input::kNotConnected);
    assert(m6input::ApplyRouteCode(r, 312, 1));  // -> user 2; user 1 stays connected and idle
    assert(m6input::RouteFor(2, r) == m6input::kSchedule && m6input::RouteFor(1, r) == m6input::kIdle);
    assert(m6input::ApplyRouteCode(r, 310, 1) && m6input::RouteFor(0, r) == m6input::kSchedule);
    assert(m6input::ApplyRouteCode(r, 321, 1) && m6input::RouteFor(1, r) == m6input::kNotConnected);  // unplug 1
    assert(m6input::ApplyRouteCode(r, 321, 0) && m6input::RouteFor(1, r) == m6input::kIdle);  // replug 1
    assert(m6input::ApplyRouteCode(r, 320, 1) && m6input::RouteFor(0, r) == m6input::kNotConnected);  // unplug sched
    assert(!m6input::ApplyRouteCode(r, 311, 0) && m6input::RouteFor(1, r) == m6input::kIdle);  // value 0: no switch
    assert(m6input::ApplyRouteCode(r, 321, 2) == false);
    m6input::Routing closed; closed.schedule_user = -1;
    assert(m6input::ApplyRouteCode(closed, 311, 1));
    for (unsigned u = 0; u < 4; ++u) assert(m6input::RouteFor(u, closed) == m6input::kNotConnected);
  }
  {  // route codes in a schedule reach the hook and are not buttons
    { std::ofstream f(path); f << "0 311 1\n0 40 1\n1 40 0\n2 321 1\n3 321 0\n"; }
    static unsigned codes[8]; static int downs[8]; static unsigned n = 0;
    m6input::Source src(path, [](unsigned scan, int down) { codes[n] = scan; downs[n] = down; ++n; });
    auto s = src.Sample(0); assert(s.buttons == 0x10 && n == 1 && codes[0] == 311 && downs[0] == 1);
    src.Sample(3); assert(n == 3 && codes[1] == 321 && downs[1] == 1 && codes[2] == 321 && downs[2] == 0);
    m6input::Source plain(path);  // no hook: codes ignored as before
    assert(plain.Sample(0).buttons == 0x10);
  }
  // G6-P79 / G6-P80: the profile handoff policy (g6p79_profile_handoff.h). G6-P80: the candidate is the title's own
  // selected user (its save-gate word), cross-checked against an unused START authorization and the connection.
  {
    using g6p79::Outcome;
    assert(!g6p79::ParseEnable(nullptr, "1") && !g6p79::ParseEnable("1", nullptr));
    assert(!g6p79::ParseEnable("1", "") && !g6p79::ParseEnable("1", "0") && !g6p79::ParseEnable("1", "true"));
    assert(!g6p79::ParseEnable("1", "1 ") && !g6p79::ParseEnable("1", "11") && g6p79::ParseEnable("", "1"));
    const bool all[4] = {true, true, true, true}, only0[4] = {true, false, false, false};
    const bool no1[4] = {true, false, true, true};
    {  // default: user 0 owns; no START by the title's user -> refused; owner is never two users
      g6p79::Policy p;
      assert(p.Owner() == 0 && p.IsOwner(0) && !p.IsOwner(1) && !p.Locked());
      auto d = p.OnSigninRequest(all, 1000, 1); assert(d.outcome == Outcome::kNoCandidate && p.Owner() == 0);
      d = p.OnSigninRequest(all, 1000, 4); assert(d.outcome == Outcome::kNoTitleUser && p.Owner() == 0);
      d = p.OnSigninRequest(all, 1000, 0xFFFFFFFFu); assert(d.outcome == Outcome::kNoTitleUser && d.candidate == 4);
    }
    {  // user 1 START, the title selected user 1: moved, exclusively; the commit witness locks it
      g6p79::Policy p;
      p.NoteStart(1, 1000);
      auto d = p.OnSigninRequest(all, 1200, 1);
      assert(d.outcome == Outcome::kMoved && d.from == 0 && d.to == 1 && p.Owner() == 1 && d.start_candidate == 1);
      unsigned owners = 0; for (unsigned u = 0; u < 4; ++u) owners += p.IsOwner(u);
      assert(owners == 1 && !p.IsOwner(0));
      assert(!p.NoteCommitWitness(0) && !p.Locked());  // a non-owner cannot lock
      assert(p.NoteCommitWitness(1) && p.Locked() && !p.NoteCommitWitness(1));
      p.NoteStart(0, 1300);  // a second START after the commit
      d = p.OnSigninRequest(all, 1400, 0); assert(d.outcome == Outcome::kLocked && p.Owner() == 1 && d.candidate == 0);
      assert(!p.OnDisconnect(1) && p.Owner() == 1);  // locked: an unplug never rolls back (D4)
    }
    {  // the title's selection wins over the most recent START (held START keeps the title on pad 2)
      g6p79::Policy p;
      p.NoteStart(1, 100); p.NoteStart(0, 150);  // pad 1 pressed last, but the title kept user 1
      auto d = p.OnSigninRequest(all, 200, 1);
      assert(d.outcome == Outcome::kMoved && p.Owner() == 1 && d.candidate == 1 && d.start_candidate == 0);
      d = p.OnSigninRequest(all, 300, 0);  // the title then selected pad 1: follows it, before any commit
      assert(d.outcome == Outcome::kMoved && d.from == 1 && p.Owner() == 0);
      d = p.OnSigninRequest(all, 350, 0); assert(d.outcome == Outcome::kSameOwner && p.Owner() == 0);
    }
    {  // G6-P80: a START authorizes one decision, with no wall-clock window; a disconnected candidate never moves
      g6p79::Policy p;
      p.NoteStart(1, 1000);
      auto d = p.OnSigninRequest(no1, 1100, 1); assert(d.outcome == Outcome::kNotConnected && p.Owner() == 0);
      d = p.OnSigninRequest(all, 1200, 1); assert(d.outcome == Outcome::kUsedStart && p.Owner() == 0);  // used up
      d = p.OnSigninRequest(only0, 1300, 1); assert(d.outcome == Outcome::kUsedStart && p.Owner() == 0);
      p.NoteStart(1, 2000);  // a fresh START; the title's request comes 10 minutes later (an unanswered box)
      d = p.OnSigninRequest(all, 2000 + 600000, 1); assert(d.outcome == Outcome::kMoved && p.Owner() == 1);
      d = p.OnSigninRequest(all, 0, 1); assert(d.outcome == Outcome::kSameOwner && p.Owner() == 1);  // clock unused
      p.NoteStart(7, 1); p.NoteStart(4, 1);  // invalid users are ignored
      d = p.OnSigninRequest(all, 1, 2); assert(d.outcome == Outcome::kNoCandidate && p.Owner() == 1);
    }
    {  // G6-P80 stale: a START made before an unplug never authorizes a request after the replug
      g6p79::Policy p;
      p.NoteStart(2, 10);
      assert(!p.OnDisconnect(2) && p.Owner() == 0);  // not the owner: nothing rolls back, but the START is void
      auto d = p.OnSigninRequest(all, 20, 2); assert(d.outcome == Outcome::kUsedStart && p.Owner() == 0);
      p.NoteStart(2, 30);  // replugged and START again
      d = p.OnSigninRequest(all, 40, 2); assert(d.outcome == Outcome::kMoved && p.Owner() == 2);
    }
    {  // G6-P80 changed selection: no ping-pong between controllers without new START presses
      g6p79::Policy p;
      p.NoteStart(1, 10); p.NoteStart(0, 12);
      auto d = p.OnSigninRequest(all, 20, 1); assert(d.outcome == Outcome::kMoved && p.Owner() == 1);
      d = p.OnSigninRequest(all, 30, 2); assert(d.outcome == Outcome::kNoCandidate && p.Owner() == 1);  // no START
      d = p.OnSigninRequest(all, 40, 0); assert(d.outcome == Outcome::kMoved && p.Owner() == 0);  // unused START
      d = p.OnSigninRequest(all, 50, 1); assert(d.outcome == Outcome::kUsedStart && p.Owner() == 0);  // back: refused
      p.NoteStart(1, 60);
      d = p.OnSigninRequest(all, 70, 1); assert(d.outcome == Outcome::kMoved && p.Owner() == 1);
    }
    {  // G6-P80 rollback: a pending owner's unplug returns the profile to user 0, never to another controller
      g6p79::Policy p;
      p.NoteStart(2, 10); p.NoteStart(1, 20);
      assert(p.OnSigninRequest(all, 30, 1).outcome == Outcome::kMoved && p.Owner() == 1);
      assert(!p.OnDisconnect(2) && !p.OnDisconnect(0) && !p.OnDisconnect(9) && p.Owner() == 1);  // not the owner
      assert(p.OnDisconnect(1) && p.Owner() == 0 && !p.Locked());
      assert(!p.OnDisconnect(1) && !p.OnDisconnect(0) && p.Owner() == 0);  // home never moves
      // the title then asks for the unplugged user again: refused (its START was used), the profile stays home
      auto d = p.OnSigninRequest(no1, 40, 1); assert(d.outcome == Outcome::kUsedStart && p.Owner() == 0);
      p.NoteStart(1, 45);  // a START reported while unplugged is still refused by the connection
      d = p.OnSigninRequest(no1, 46, 1); assert(d.outcome == Outcome::kNotConnected && p.Owner() == 0);
      p.NoteStart(1, 50);  // replugged and START again: moves again, then commits
      d = p.OnSigninRequest(all, 60, 1); assert(d.outcome == Outcome::kMoved && p.Owner() == 1);
      assert(p.NoteCommitWitness(1) && !p.OnDisconnect(1) && p.Owner() == 1);
    }
    {  // locked at user 0 (a normal pad-1 game): no later START moves it
      g6p79::Policy p;
      assert(p.NoteCommitWitness(0));
      p.NoteStart(1, 10);
      auto d = p.OnSigninRequest(all, 20, 1); assert(d.outcome == Outcome::kLocked && p.Owner() == 0);
      assert(!p.OnDisconnect(0) && p.OnSigninRequest(all, 30, 1).outcome == Outcome::kLocked && p.Owner() == 0);
    }
    // The runtime wrappers stay disabled in this process (no R3HD_NONINTRUSIVE / flag): owner 0, nothing recorded.
    assert(!g6p79::Enabled() && g6p79::Owner() == 0 && g6p79::IsOwner(0) && !g6p79::IsOwner(1));
    g6p79::NoteStart(1, g6p79::NowMs()); assert(!g6p79::NoteCommitWitness(0) && g6p79::Owner() == 0);
    assert(!g6p79::OnDisconnect(0) && !g6p79::OnDisconnect(1) && g6p79::Owner() == 0);
  }
  // G6-P80: user-scoped schedule events (m6_test_input.h UserEvents).
  {
    using N = m6input::UeNote;
    struct Notes { std::vector<N> v; void push_back(const N& n) { v.push_back(n); } };
    assert(!m6input::ParseUserEvents(nullptr, "1") && !m6input::ParseUserEvents("1", nullptr));
    assert(!m6input::ParseUserEvents("1", "") && !m6input::ParseUserEvents("1", "11") && !m6input::ParseUserEvents("1", "true"));
    assert(m6input::ParseUserEvents("", "1") && !m6input::UserEventsEnabled() && m6input::TakeDialogAnswer() == -1);
    {  // initial presence equals the G6-P77 routing: user 0 and the test user
      for (int t = 0; t < 4; ++t) {
        m6input::UserEvents e(t);
        for (unsigned u = 0; u < 4; ++u) assert(e.Present(u) == (m6input::RouteFor(u, t) != m6input::kNotConnected));
      }
      m6input::UserEvents closed(-1); Notes n;
      for (unsigned u = 0; u < 4; ++u) assert(!closed.Present(u));
      closed.Apply(311, 1, n); closed.Apply(40, 1, n);
      assert(!closed.Present(1) && n.v.size() == 1 && n.v[0].kind == N::kDrop);  // fail closed stays closed
    }
    {  // a press belongs to the user targeted when its line is applied; only that user's poll delivers it
      m6input::UserEvents e(1); Notes n;
      e.Apply(40, 1, n); e.Apply(40, 0, n);  // pad 2 START (press + release in one batch)
      e.Apply(310, 1, n); e.Apply(40, 1, n);  // then target pad 1 and press START: same batch, no cross-delivery
      assert(n.v.size() == 3 && n.v[0].kind == N::kQueued && n.v[0].user == 1 && n.v[1].kind == N::kTarget &&
             n.v[2].kind == N::kQueued && n.v[2].user == 0 && n.v[2].seq == 2);
      n.v.clear();
      assert(e.Sample(2, true, n).buttons == 0 && n.v.empty());  // another user sees nothing
      assert(e.Sample(1, false, n).buttons == 0x10 && n.v.empty());  // a null query does not consume
      assert(e.Sample(1, true, n).buttons == 0x10 && n.v.size() == 1 && n.v[0].kind == N::kDeliver &&
             n.v[0].user == 1 && n.v[0].seq == 1);
      assert(e.Sample(1, true, n).buttons == 0);  // released
      n.v.clear();
      assert(e.Sample(0, true, n).buttons == 0x10 && n.v.size() == 1 && n.v[0].user == 0 && n.v[0].seq == 2);
      e.Apply(40, 0, n);
      assert(e.Sample(0, true, n).buttons == 0);
    }
    {  // connection state is per user and independent of the target; events for an unplugged target are dropped
      m6input::UserEvents e(1); Notes n;
      e.Apply(40, 1, n);  // pad 2 holds START
      e.Apply(321, 1, n);  // unplug pad 2: its held and pending input is cleared
      assert(!e.Present(1) && e.Present(0) && n.v.back().kind == N::kConnect && n.v.back().value == 0);
      e.Apply(40, 0, n); e.Apply(40, 1, n);  // the schedule still targets pad 2: dropped, not redirected
      assert(n.v.back().kind == N::kDrop && n.v.back().user == 1);
      assert(e.Sample(0, true, n).buttons == 0);
      e.Apply(310, 1, n); e.Apply(44, 1, n);  // target pad 1 while pad 2 is unplugged: works (G6-P79 could not)
      assert(e.Sample(0, true, n).buttons == 0x1000);
      e.Apply(44, 0, n);
      e.Apply(321, 0, n);  // replug pad 2 while pad 1 is targeted
      assert(e.Present(1) && n.v.back().kind == N::kConnect && n.v.back().value == 1);
      Notes m; assert(e.Sample(1, true, m).buttons == 0 && m.v.empty());  // replugged neutral
      e.Apply(311, 1, n); e.Apply(40, 1, n);
      assert(e.Sample(1, true, m).buttons == 0x10 && m.v.size() == 1 && m.v[0].kind == N::kDeliver);
      e.Apply(320, 1, n); assert(!e.Present(0));  // user 0 may also be unplugged
      e.Apply(323, 0, n); assert(e.Present(3));  // replugging an unseen user makes it present
      e.Apply(321, 7, n); e.Apply(311, 0, n); assert(e.Present(1));  // invalid values are ignored
    }
    {  // dialog answers are queued in order, bounded
      m6input::UserEvents e(0); Notes n;
      e.Apply(340, 1, n); e.Apply(341, 1, n); e.Apply(344, 1, n); e.Apply(341, 0, n);
      assert(e.TakeAnswer() == 0 && e.TakeAnswer() == 1 && e.TakeAnswer() == -1);
      for (unsigned i = 0; i < m6input::kUeAnswers + 2; ++i) e.Apply(341, 1, n);
      assert(n.v.back().kind == N::kAnswerDrop);
    }
    {  // bounded lines
      m6input::UserEvents e(0); Notes n;
      for (unsigned i = 0; i < m6input::kUeMaxLines + 10; ++i) e.Apply(40, int(i % 2 == 0), n);
      assert(e.Lines() == m6input::kUeMaxLines && n.v.back().kind == N::kLimit);
    }
  }
  // G6-P82 / G6-P83 (D-332): state-change-aware XN_SYS_SIGNINCHANGED from XamShowSigninUI by default
  // (g6p82_signin_notify.h); R3HD_SIGNIN_NOTIFY exactly "legacy" is the switch back.
  {
    assert(g6p82::ParseLegacy("legacy"));
    assert(!g6p82::ParseLegacy(nullptr) && !g6p82::ParseLegacy("") && !g6p82::ParseLegacy("Legacy"));
    assert(!g6p82::ParseLegacy("legacy ") && !g6p82::ParseLegacy(" legacy") && !g6p82::ParseLegacy("1"));
    assert(!g6p82::ParseLegacy("0") && !g6p82::ParseLegacy("on_change") && !g6p82::ParseLegacy("legacyx"));
    for (unsigned b = 0; b < 4; ++b)
      for (unsigned a = 0; a < 4; ++a) {
        assert(g6p82::Decide(false, b, a));             // legacy: always, as inherited
        assert(g6p82::Decide(true, b, a) == (b != a));  // default: only on an owner change
      }
    assert(!g6p82::Decide(true, 0, 0) && g6p82::Decide(true, 0, 1) && g6p82::Decide(true, 1, 0));
    // The process policy follows the environment exactly. Without the switch back (the build's case) the default
    // suppresses a no-change call, notifies a change and never asks for the legacy note; with it, the inherited
    // stub notifies every call and the note is asked for exactly once.
    if (!g6p82::ParseLegacy(std::getenv("R3HD_SIGNIN_NOTIFY"))) {
      assert(!g6p82::Legacy() && g6p82::Enabled() && !g6p82::NoteLegacyOnce() && !g6p82::NoteLegacyOnce());
      assert(!g6p82::ShouldNotify(0, 0) && g6p82::ShouldNotify(0, 1));
    } else {
      assert(g6p82::Legacy() && !g6p82::Enabled() && g6p82::NoteLegacyOnce() && !g6p82::NoteLegacyOnce());
      assert(g6p82::ShouldNotify(0, 0) && g6p82::ShouldNotify(0, 1));
    }
  }
  assert(std::remove(path) == 0);
  { std::ifstream removed(path); assert(!removed.good()); }
  std::puts("M6 input PASS: null-query retention, edges, packets, axes, analog axes, partial/follow append, test user routing, G6-P79 route codes, G6-P79/G6-P80 handoff policy and rollback, G6-P80 user-scoped events, G6-P82/G6-P83 signin notify default and legacy switch back");
}
