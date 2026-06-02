"""
Unit tests for the outreach/sales-engine modules.

Runnable two ways:
  • pytest:        pytest tests/test_modules.py
  • plain script:  python3 tests/test_modules.py   (no pytest needed)

Tests that touch a CSV/parquet store point the module's path constant at a
tempdir, so nothing here writes to real data/.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── outreach_email ─────────────────────────────────────────────────
def test_outreach_email_numbers_and_greeting():
    import outreach_email as oe
    e = oe.compose_email(system_name="Banner Health", annual_savings=18_400_000,
                         term_impact=36_800_000, rn_need=420, monthly_fee=2_940_000,
                         contact_name="Dana Reyes")
    assert "$18.4M" in e["subject"]
    assert e["body"].startswith("Hi Dana,")
    assert "$7K per nurse / month" in e["body"]
    assert e["mailto"].startswith("mailto:?")
    txt = oe.as_txt(e)
    assert "SUBJECT OPTIONS" in txt and "BODY" in txt


def test_outreach_sequence_four_steps():
    import outreach_email as oe
    seq = oe.compose_sequence(system_name="Banner Health", annual_savings=18.4e6,
                              term_impact=36.8e6, rn_need=420, monthly_fee=2.94e6,
                              contact_name="Dana Reyes")
    assert [s["step"] for s in seq] == [1, 2, 3, 4]
    assert all(s.get("subject") and s.get("body") and s.get("mailto") for s in seq)
    txt = oe.sequence_as_txt(seq)
    assert "STEP 1" in txt and "STEP 4" in txt and "Breakup" in txt


def test_outreach_email_no_contact_uses_placeholder():
    import outreach_email as oe
    e = oe.compose_email(system_name="X Health", annual_savings=1e6, term_impact=2e6,
                         rn_need=0, monthly_fee=0)
    assert "[First name]" in e["body"]


def test_ai_opener_rule_fallback():
    import os, re, ai_opener as A
    os.environ.pop("ANTHROPIC_API_KEY", None)
    assert A.is_configured() is False
    r = A.generate({"system_name": "Banner Health", "n_facilities": 30, "rn_need": 420,
                    "annual_savings": 18.4e6})
    assert r["source"] == "rule" and "Banner Health" in r["opener"]
    assert not re.search(r"\b(fica|visa|tax|immigration)\b", r["opener"].lower())
    import outreach_email as oe
    e = oe.compose_email(system_name="Banner Health", annual_savings=18.4e6, term_impact=36.8e6,
                         rn_need=420, monthly_fee=2.94e6, contact_name="Dana Reyes",
                         opener=r["opener"])
    assert r["opener"] in e["body"] and "I lead health-system partnerships" not in e["body"]


# ─── lob_mailer ─────────────────────────────────────────────────────
def test_retrieval_code_format():
    import lob_mailer as L
    c = L.retrieval_code()
    assert c.startswith("FLOR-") and len(c) == 10
    assert not (set("O0I1") & set(c[5:]))  # ambiguous chars removed


def test_mailpiece_renderers():
    import lob_mailer as L
    ltr = L.render_letter_html(org_name="Sutter Health", contact_name="Dana Reyes",
                               monthly_fee=2_940_000, term_impact=36_800_000, rn_need=420,
                               code="FLOR-7QK4M")
    assert ltr.lstrip().startswith("<!doctype html>") and "8.5in 11in" in ltr and "18.4M" in ltr
    pc = L.render_postcard_html(org_name="Sutter Health", monthly_fee=2_940_000,
                                term_impact=36_800_000, rn_need=420)
    assert set(pc) == {"front", "back"} and "11in 6in" in pc["front"]
    prev = L.preview_html("letter", org_name="Sutter", term_impact=1e7, rn_need=120)
    assert "iframe" in prev


def test_record_outcome_halts_cadence(tmp_store):
    import lob_mailer as L, sales_intel as S
    L.MAIL_LOG = tmp_store / "mail.csv"
    assert L.record_outcome("system", "sys1", "Replied", org_name="X")
    assert S.cadence_next("system", "sys1").get("done") is True


# ─── sales_intel ────────────────────────────────────────────────────
def test_reachability_bounds():
    import sales_intel as S
    full = S.reachability({"contact_name": "A", "phone": "p", "email": "e", "mailable": True})
    assert full["pct"] == 100 and full["label"] == "Reachable"
    none = S.reachability({})
    assert none["pct"] == 0 and none["label"] == "No contact"


def test_priority_reachable_outranks():
    import sales_intel as S
    assert S.priority_score(1e6, 1.0) > S.priority_score(1e6, 0.0)
    recs = [{"health_system_id": "a", "health_system": "Alpha", "term_savings_target": 50e6,
             "rn_need": 400, "monthly_fee_target": 2.8e6},
            {"health_system_id": "b", "health_system": "Beta", "term_savings_target": 80e6,
             "rn_need": 600, "monthly_fee_target": 4.1e6}]
    gc = lambda et, eid: ({"contact_name": "X", "phone": "p", "email": "e", "mailable": True}
                          if eid == "a" else {})
    ranked = S.rank_systems(recs, gc)
    assert ranked[0]["name"] == "Alpha"  # reachable $50M beats unreachable $80M


def test_cadence_first_step():
    import sales_intel as S
    c = S.cadence_next("system", "__never_touched__")
    assert c["step"] == 1 and c["ready"] and not c["done"]


# ─── email_discovery ────────────────────────────────────────────────
def test_email_patterns_and_normalize():
    import email_discovery as E
    c = E.candidate_emails("Dana Reyes", "hcahealthcare.com")
    assert c[0]["email"] == "dana.reyes@hcahealthcare.com"
    assert E.normalize_domain("https://www.Sutter.org/x") == "sutter.org"
    assert E.candidate_emails("Dr. Alex P. Rivera III", "providence.org")[0]["email"] == "alex.rivera@providence.org"
    assert E.candidate_emails("Reception", "x.com") == []
    assert E.candidate_emails("Dana Reyes", "") == []


# ─── call_script ────────────────────────────────────────────────────
def test_call_script_build():
    import call_script as C
    s = C.build_script(system_name="Banner", annual_savings=18_400_000, term_impact=36_800_000,
                       rn_need=420, monthly_fee=2_940_000, contact_name="Dana Reyes",
                       contact_phone="(602) 555-0144")
    assert s["numbers"]["hero_annual"] == "$18.4M" and len(s["objections"]) >= 4
    assert "Dana" in s["opening"] and "(602) 555-0144" in C.as_text(s)


# ─── contacts ───────────────────────────────────────────────────────
def test_contacts_bulk_import(tmp_store):
    import contacts as C, pandas as pd
    C.OVERRIDES = tmp_store / "ov.csv"
    df = pd.DataFrame([
        {"entity_type": "system", "entity_id": "hca", "contact_name": "Dana Reyes", "email": "d@x.com"},
        {"system_name": "HCA Healthcare", "title": "CNO"},        # resolves by name → merge
        {"org_name": "Totally Unknown Org 999", "contact_name": "Z"},  # unresolvable → skip
    ])
    res = C.bulk_import(df, by="rep@florenceeducation.com")
    assert res["imported"] == 2 and res["skipped"] == 1
    c = C.get_contact("system", "hca")
    assert c["contact_name"] == "Dana Reyes" and c["email"] == "d@x.com" and c["title"] == "CNO"
    assert C.export_overrides_csv().splitlines()[0].startswith("entity_type")


# ─── activity ───────────────────────────────────────────────────────
def test_activity_timeline_merges_mail(tmp_store):
    import activity as A, lob_mailer as L
    A.LOG = tmp_store / "act.csv"
    L.MAIL_LOG = tmp_store / "mail.csv"
    A.log("system", "hca", "call", "Left VM with CNO", org_name="HCA")
    L.record_outcome("system", "hca", "Replied", org_name="HCA")
    tl = A.timeline("system", "hca")
    kinds = {e["kind"] for e in tl}
    assert "call" in kinds and "outcome" in kinds
    assert tl == sorted(tl, key=lambda r: r["ts"], reverse=True)
    assert len(A.search("vm")) >= 1


# ─── funnel ─────────────────────────────────────────────────────────
def test_funnel_counts(tmp_store):
    import funnel as F, pandas as pd
    pd.DataFrame([
        {"entity_type": "system", "entity_id": "a", "status": "drafted", "by": "r1"},
        {"entity_type": "system", "entity_id": "b", "status": "responded", "by": "r2"},
    ]).to_csv(tmp_store / "mail.csv", index=False)
    pd.DataFrame([{"code": "FLOR-AAA"}]).to_csv(tmp_store / "acts.csv", index=False)
    pd.DataFrame([{"deal_id": "d1", "rep_email": "r2", "system_id": "b", "stage": "closed_won"}]
                 ).to_csv(tmp_store / "pipe.csv", index=False)
    F.MAIL, F.ACTS, F.PIPE = tmp_store / "mail.csv", tmp_store / "acts.csv", tmp_store / "pipe.csv"
    c = F.funnel_counts()
    assert c["Outreach drafted"] == 2 and c["Responded"] == 1 and c["Hired (won)"] == 1
    assert not F.by_rep().empty


# ─── crm_sync (dormant) ─────────────────────────────────────────────
def test_crm_sync_dry_runs():
    import os, crm_sync as X
    for k in ("GMAIL_TOKEN_FILE", "STREAK_API_KEY", "STREAK_PIPELINE_KEY"):
        os.environ.pop(k, None)
    assert X.create_gmail_draft(to="x@y.com", subject="s", body="b")["mode"] == "dry_run"
    assert X.streak_upsert_box(name="X")["mode"] == "dry_run"


# ─── ownership ──────────────────────────────────────────────────────
def test_ownership_assign_book(tmp_store):
    import ownership as O
    O.OWNERS = tmp_store / "owners.csv"
    O.assign("hca", "Rep@FlorenceEducation.com", by="admin@x")
    O.assign("sutter_health", "rep@florenceeducation.com")
    assert O.owner_of("hca") == "rep@florenceeducation.com"   # normalized lower
    assert O.book_of("rep@florenceeducation.com") == {"hca", "sutter_health"}
    O.unassign("hca")
    assert O.owner_of("hca") == "" and O.book_of("rep@florenceeducation.com") == {"sutter_health"}


# ─── florence_auth ──────────────────────────────────────────────────
def test_auth_open_and_domain():
    import os, florence_auth as A
    os.environ.pop("FLORENCE_ALLOWED_DOMAIN", None)

    class _St:
        secrets = {}
    assert A.is_configured(_St()) is False
    assert A.require_login(_St()) is None           # open mode → no gate
    assert A._allowed_domains(_St()) == {"florenceeducation.com"}


# ─── pytest fixture / script-mode shim ──────────────────────────────
def _make_tmp_store():
    return Path(tempfile.mkdtemp())


try:
    import pytest

    @pytest.fixture()
    def tmp_store():
        return _make_tmp_store()
except Exception:  # pytest absent (script mode)
    pytest = None


if __name__ == "__main__":
    import inspect
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            kwargs = {"tmp_store": _make_tmp_store()} if "tmp_store" in inspect.signature(fn).parameters else {}
            fn(**kwargs)
            print(f"PASS  {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
