from app.requirement_language import is_context_only_statement
from app.requirements import capture_explicit_requirements


def test_preserving_saved_fields_does_not_create_a_new_travel_requirement():
    text='其他活动、午餐留白、日期、交通方式和个人偏好都保持原样'
    assert is_context_only_statement(text)
    assert capture_explicit_requirements([],text,scope={'kind':'trip','trip_id':'fixture'},source_ref='fixture')==[]
    assert not is_context_only_statement('个人偏好改为不喝酒')
    assert not is_context_only_statement('其他预算最多100元保持原样')
