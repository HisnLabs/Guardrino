def test_new_module_name():
    from guardrino_litellm import GuardrinoGuardrail
    assert GuardrinoGuardrail.__name__ == "GuardrinoGuardrail"


def test_old_import_still_works():
    import guardrino_guardrail
    from guardrino_litellm import GuardrinoGuardrail
    assert guardrino_guardrail.GuardrinoGuardrail is GuardrinoGuardrail
