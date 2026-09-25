from vigia.difftext import extract_diff


def test_added_and_removed_sentences_are_reported():
    result = extract_diff("Keep this. Remove this.", "Keep this. Add this.")
    assert result["added"] == ["Add this."]
    assert result["removed"] == ["Remove this."]
    assert result["before"] == "Remove this."
    assert result["after"] == "Add this."


def test_added_and_removed_pure_diffs():
    assert extract_diff("A. B.", "A. B. C.")["added"] == ["C."]
    assert extract_diff("A. B. C.", "A. B.")["removed"] == ["C."]


def test_price_change_has_before_and_after():
    result = extract_diff("The plan costs $10 per month.", "The plan costs $12 per month.")
    assert result["before"] == "The plan costs $10 per month."
    assert result["after"] == "The plan costs $12 per month."


def test_empty_when_nothing_changes():
    assert extract_diff("A sentence. Same.", "A sentence. Same.") == {
        "added": [], "removed": [], "before": "", "after": ""
    }


def test_priority_phrases_survive_limit():
    filler = " ".join(f"Filler sentence number {i}." for i in range(250))
    result = extract_diff(filler, filler + " Pricing is now $99 per month. Removed support is deprecated.")
    assert "Pricing is now $99 per month." in result["after"]
    assert len(result["after"]) <= 4000
