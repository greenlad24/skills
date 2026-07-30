from __future__ import annotations

from app.modules.research.swipe import guardrail


SOURCE = "เมื่อก่อนหน้าฉันเป็นสิวหนักมากจนได้ลองตัวนี้แล้วชีวิตเปลี่ยนไปเลยหน้าใสขึ้นมาก"


def test_similarity_gate_blocks_near_verbatim():
    # generated copy reuses a long verbatim span from the source
    generated = "สวัสดีค่ะ " + SOURCE + " ลองดูนะคะ"
    res = guardrail.similarity_gate(generated, [SOURCE], n=7)
    assert res.passed is False
    assert res.offending_spans


def test_similarity_gate_passes_original():
    generated = "ผลิตภัณฑ์ตัวนี้ช่วยเรื่องผิวได้ดีในแบบของเราเอง ลองพิจารณาดูค่ะ"
    res = guardrail.similarity_gate(generated, [SOURCE], n=7)
    assert res.passed is True
    assert res.offending_spans == []


def test_self_duplicate_detection():
    a = "รีวิวเซรั่มตัวนี้ ใช้แล้วผิวดีขึ้น หน้าใส เหมาะกับทุกสภาพผิว แนะนำเลย"
    near = "รีวิวเซรั่มตัวนี้ ใช้แล้วผิวดีขึ้น หน้าใส เหมาะกับทุกสภาพผิว แนะนำมากๆ"
    far = "วันนี้พาไปกินร้านอาหารญี่ปุ่นสุดอร่อยในกรุงเทพ บรรยากาศดีมาก"
    assert guardrail.is_self_duplicate(near, [a]) is True
    assert guardrail.is_self_duplicate(far, [a]) is False


def test_assert_template_clean():
    clean = ["ใครที่ {problem} ห้ามพลาด", "{timeframe} เห็นผล {benefit}"]
    dirty = [SOURCE[:40]]  # a copied source span
    assert guardrail.assert_template_clean(clean, [SOURCE]) == []
    assert guardrail.assert_template_clean(dirty, [SOURCE]) != []
