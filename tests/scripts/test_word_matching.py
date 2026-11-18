"""Words of the plan matched against the transcript (review 2026-11-17, #8 and #9).

- A scene or an insert placed by a spoken word (`word:don't#1`) finds the word as the transcript has it, whatever
  punctuation the word carries: an apostrophe, a percent sign, a dollar sign.
- A line in German, French or Turkish is counted by its real words: a letter outside a-z and the Russian alphabet
  (u-umlaut, e-acute, s-cedilla) does not cut a word in two, so a 4-word hook is not refused as longer than 6 words.
"""
import pytest

from vp_core import norm_words, resolve_at


def cap(*texts):
    return {"words": [{"text": t, "start": float(k), "end": k + 0.4} for k, t in enumerate(texts)]}


@pytest.mark.parametrize("word, spoken", [("don't", "don't"), ("50%", "50%"), ("$100", "$100"),
                                          ("it's", "It's,")])
def test_a_word_with_punctuation_is_found(word, spoken):
    c = cap("so", "we", spoken, "now")
    assert resolve_at(f"word:{word}#1", {"segments": []}, c) == 2.0


def test_a_word_in_another_alphabet_is_found():
    c = cap("wir", "planen", "für", "München")
    assert resolve_at("word:münchen#1", {"segments": []}, c) == 3.0


@pytest.mark.parametrize("text, n", [
    ("Grüße aus München heute", 4),            # German
    ("Le résumé est prêt", 4),                  # French
    ("Başarı çok güzel", 3),                # Turkish
    ("résumé prêt", 2),                        # e + a combining accent (typed on a Mac)
    ("So today we talk", 4),
])
def test_words_are_counted_whole_in_any_latin_language(text, n):
    assert len(norm_words(text)) == n
