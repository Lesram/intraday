def test_light_mode_torch_mock():
    """Test that torch is mocked in light mode"""
    import torch
    assert torch.__file__ == "<mocked:torch>"
    assert torch.cuda.is_available() == False
    print(f"✅ Light mode working: torch is mocked as {torch}")

def test_light_mode_transformers_mock():
    """Test that transformers is mocked in light mode"""
    import transformers
    assert transformers.__file__ == "<mocked:transformers>"
    print(f"✅ Light mode working: transformers is mocked as {transformers}")
