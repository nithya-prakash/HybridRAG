from app.core.config import Settings
from app.core.reranker import (
    BASELINE_RERANKER_MODEL,
    CrossEncoderReranker,
    resolve_reranker_model_name,
)


def test_reranker_model_baseline_alias_resolves_to_the_shipped_model():
    settings = Settings(reranker_model="baseline")

    assert resolve_reranker_model_name(settings) == BASELINE_RERANKER_MODEL


def test_reranker_model_finetuned_alias_resolves_to_configured_path():
    settings = Settings(
        reranker_model="finetuned", reranker_finetuned_path="/some/checkpoint/dir"
    )

    assert resolve_reranker_model_name(settings) == "/some/checkpoint/dir"


def test_reranker_model_raw_hf_id_passes_through_untouched():
    settings = Settings(reranker_model="cross-encoder/some-other-model")

    assert resolve_reranker_model_name(settings) == "cross-encoder/some-other-model"


def test_reranker_model_default_is_the_baseline():
    settings = Settings()

    assert resolve_reranker_model_name(settings) == BASELINE_RERANKER_MODEL


def test_cross_encoder_reranker_constructs_from_settings_without_explicit_override():
    reranker = CrossEncoderReranker()

    assert reranker._model_name == BASELINE_RERANKER_MODEL


def test_cross_encoder_reranker_explicit_model_name_bypasses_settings_entirely():
    # The A/B comparison script (eval/reranker_training/
    # evaluate_baseline_vs_finetuned.py) needs two live instances with
    # different models at once, without mutating process-wide settings
    # between them — this is what makes that possible.
    reranker = CrossEncoderReranker(model_name="/an/explicit/path")

    assert reranker._model_name == "/an/explicit/path"
