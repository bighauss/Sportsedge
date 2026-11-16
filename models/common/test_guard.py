from guard import is_input_gap, exposure_group

def test_raiders_ml_hidden():
    assert is_input_gap(0.445, 0.285)

def test_cardinals_ml_borderline_passes():
    assert not is_input_gap(0.302, 0.202)

def test_normal_edge_shown():
    assert not is_input_gap(0.55, 0.50)

def test_groups():
    assert exposure_group("LV_SEA", "ML", "LV") == exposure_group("LV_SEA", "Spread", "LV")
    assert exposure_group("LV_SEA", "Over", "") != exposure_group("LV_SEA", "ML", "LV")
