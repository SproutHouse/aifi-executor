#!/usr/bin/env python3
"""Manual controls. --flatten sets HALT first, then closes everything now; --halt "reason" stops new entries;
--resume clears HALT. --fleet-halt "reason" / --fleet-resume do the same for EVERY agent at once (state/FLEET_HALT).
Exits are never blocked by any halt.

The agent (EXECUTOR_AGENT) must be "core" or an id in agents/index.json: a typo ("arena-1") used to write a kill switch
no cycle reads and report "halted" while the real agent kept trading. The fleet switches need no agent."""
import argparse, sys, _path  # noqa: F401
from executor import common as C, ledger as L, paper as PA
from executor.cycle import Cycle, HALT


def known_agent(aid):
    return aid == "core" or aid in {a["id"] for a in C.agents()}


def set_halt(reason):
    HALT.parent.mkdir(parents=True, exist_ok=True)
    HALT.write_text(reason)
    HALT.with_name("HALT.since").write_text(C.iso())


def flatten():
    """HALT first, so nothing can enter while (or after) a close fails; then each position is closed inside its own
    error boundary, a carry pair through its two-leg path. Exits non-zero when anything is left open."""
    set_halt(f"manual flatten {C.iso()}")
    cy = Cycle(dry=False)
    cy.load_market()
    cy.load_account()
    left = []
    for coin, pos in list(cy.positions.items()):
        mark = cy.marks.get(coin)
        try:
            if pos.get("kind") != "carry" and not mark:
                raise RuntimeError("no mark price")
            px = mark
            if mark and cy.mode == "paper":        # a paper fill is worse than the mark: a short buys back above it
                slip = cy.s["paper_slippage_pct"] / 100
                px = mark * (1 + slip) if PA.is_short(pos) else mark * (1 - slip)
            cy.close_position(coin, pos, px, "manual flatten", cy.now)
        except Exception as e:  # noqa: BLE001 — one position's failure must not stop the others
            cy.say(f"{coin}: flatten failed ({type(e).__name__}: {str(e)[:100]}); position kept")
        if coin in cy.positions:
            left.append(coin)
    if cy.mode == "paper":
        PA.save_pot(cy.pot)
    L.save_positions(cy.positions, cy.mode)
    L.render_markdown(cy.positions, cy.summary, cy.mode)
    if left:
        C.notify("Executor: flatten incomplete", f"HALT set; still open: {', '.join(left)}. Run flatten again, or close them by hand",
                 "urgent" if cy.mode == "live" else "high")
    else:
        C.notify("Executor: flattened", f"{len(cy.summary)} actions; HALT set")
    print("\n".join(cy.summary) or "nothing to close")
    if left:
        sys.exit(f"still open after flatten: {', '.join(left)} (HALT is set)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flatten", action="store_true")
    ap.add_argument("--halt", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--fleet-halt", default=None, help="stop new entries on EVERY agent (exits still run)")
    ap.add_argument("--fleet-resume", action="store_true")
    a = ap.parse_args()
    if a.fleet_resume:
        C.FLEET_HALT.unlink(missing_ok=True)
        C.FLEET_HALT.with_name("FLEET_HALT.since").unlink(missing_ok=True)
        C.notify("Executor: fleet resumed", "fleet halt cleared; every agent may enter again from its next cycle")
        print("fleet resumed"); return
    if a.fleet_halt is not None:
        C.FLEET_HALT.parent.mkdir(parents=True, exist_ok=True)
        C.FLEET_HALT.write_text(a.fleet_halt or "manual fleet halt")
        C.FLEET_HALT.with_name("FLEET_HALT.since").write_text(C.iso())
        C.notify("Executor: FLEET HALTED", (a.fleet_halt or "manual") + " · no agent enters; exits still run")
        print("fleet halted"); return
    if not (a.resume or a.halt is not None or a.flatten):
        ap.print_help(); return
    if not known_agent(C.AGENT):
        sys.exit(f"no agent {C.AGENT!r} in agents/index.json: nothing done. Use the id shown on the dashboard (e.g. arena-01), or core.")
    if a.resume:
        if HALT.exists():
            HALT.unlink()
        HALT.with_name("HALT.since").unlink(missing_ok=True)   # dashboard: "halted since"
        C.notify("Executor: resumed", "HALT cleared; entries allowed again from the next cycle")
        print("resumed"); return
    if a.halt is not None:
        set_halt(a.halt or "manual halt"); C.notify("Executor: halted", a.halt or "manual halt"); print("halted"); return
    flatten()


if __name__ == "__main__":
    main()
