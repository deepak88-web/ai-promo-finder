
import re
from collections import Counter, defaultdict
from itertools import combinations


MAX_BUCKET_SIZE = 120
MAX_PAIRS_PER_EVENT = 8
MIN_SHARED_KEYWORDS = 2
MIN_COMPATIBILITY_SCORE = 10

STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "your",
    "her", "his", "him", "she", "he", "they", "them", "their",
    "this", "that", "these", "those", "with", "from", "into",
    "upon", "over", "under", "between", "about", "after",
    "before", "through", "while", "where", "when", "what",
    "which", "who", "whom", "whose", "how", "why", "all",
    "any", "some", "each", "every", "both", "other", "another",
    "such", "same", "own", "its", "our", "ours", "we", "us",
    "was", "were", "been", "being", "have", "has", "had",
    "having", "does", "did", "doing", "done", "can", "could",
    "would", "should", "will", "shall", "may", "might", "must",
    "am", "is", "be", "get", "got", "gets", "go", "goes",
    "went", "come", "comes", "came", "make", "made", "take",
    "takes", "took", "give", "gave", "let", "lets", "seem",
    "seems", "look", "looks", "scene", "camera", "shot",
    "close", "wide", "cut", "fade", "appears", "turns",
    "moves", "stands", "sits", "suddenly", "begins",
    "continues", "starts", "moment", "someone", "something",
    "anything", "everything", "nothing", "really", "just",
    "very", "quite", "still", "even", "back", "away",
    "there", "here", "then", "now", "again", "also",
    "only", "more", "most", "much", "many", "well", "too",
    "one", "two", "first", "last", "medium"
}


THEME_KEYWORDS = {
    "betrayal": {
        "betray", "betrayed", "betrayal", "cheat", "cheated",
        "deceive", "deceived", "deception", "unfaithful"
    },
    "love": {
        "love", "loved", "lover", "romance", "romantic",
        "kiss", "kissing", "affection", "beloved"
    },
    "revenge": {
        "revenge", "avenge", "punish", "punishment",
        "payback", "destroy", "ruin", "retaliate"
    },
    "conflict": {
        "fight", "fighting", "argue", "argument", "confront",
        "confrontation", "threat", "threatens", "attack"
    },
    "secrets": {
        "secret", "secrets", "hidden", "reveal", "reveals",
        "revealed", "truth", "mystery", "identity"
    },
    "family": {
        "mother", "father", "sister", "brother", "daughter",
        "son", "family", "wife", "husband", "marriage"
    },
    "power": {
        "duke", "king", "queen", "lord", "power", "wealth",
        "rich", "royal", "authority", "control", "crown"
    },
    "danger": {
        "danger", "dangerous", "kill", "death", "dead",
        "murder", "weapon", "blood", "escape", "arrest"
    },
    "humiliation": {
        "humiliate", "humiliated", "shame", "embarrass",
        "rejected", "insult", "insulted", "mock", "mocking"
    },
    "trust": {
        "trust", "trusted", "promise", "promised",
        "abandon", "abandoned", "faith", "loyal"
    },
    "hope": {
        "hope", "hopeful", "dream", "dreams", "future",
        "freedom", "rescue", "save", "saved"
    },
    "weakness": {
        "weak", "weakness", "powerless", "helpless",
        "vulnerable", "defenseless", "fragile", "fearful"
    },
    "sacrifice": {
        "sacrifice", "sacrificed", "sacrifice", "protect",
        "protected", "protection", "selfless"
    }
}


# These relationships allow contrasting moments to be discovered.
CONTRAST_THEMES = {
    frozenset({"humiliation", "revenge"}),
    frozenset({"weakness", "power"}),
    frozenset({"love", "betrayal"}),
    frozenset({"trust", "betrayal"}),
    frozenset({"hope", "danger"}),
    frozenset({"sacrifice", "power"}),
    frozenset({"love", "revenge"}),
    frozenset({"secrets", "trust"}),
    frozenset({"humiliation", "power"}),
    frozenset({"hope", "conflict"})
}


def tokenize(text):
    """Extract meaningful lowercase keywords."""
    words = re.findall(r"[a-zA-Z]{3,}", str(text).lower())

    return {
        word for word in words
        if word not in STOPWORDS
    }


def detect_themes(text):
    """Identify themes using a transparent keyword dictionary."""
    words = tokenize(text)
    detected = []

    for theme, keywords in THEME_KEYWORDS.items():
        if words.intersection(keywords):
            detected.append(theme)

    return detected


def build_layer1_event_metadata(layer1_selections):
    """Map Layer 1 selection information to original event IDs."""
    metadata = defaultdict(list)

    for selection in layer1_selections:
        for event_id in selection.get("event_ids", []):
            metadata[event_id].append({
                "selection_id": selection.get("selection_id"),
                "event_category": selection.get("event_category"),
                "importance": selection.get("importance"),
                "description": selection.get("description"),
                "promotional_reason": selection.get("promotional_reason"),
                "hook_potential": selection.get("hook_potential"),
                "ending_potential": selection.get("ending_potential"),
                "requires_context": selection.get("requires_context")
            })

    return metadata


def build_candidate_event_mapping(evaluated_candidates):
    """Map screenplay event IDs to existing candidate IDs."""
    mapping = defaultdict(list)

    for candidate in evaluated_candidates:
        for event_id in candidate.get("event_ids", []):
            mapping[event_id].append(candidate.get("candidate_id"))

    return mapping


def build_event_profiles(data):
    """Build searchable profiles for all screenplay events."""
    layer1_metadata = build_layer1_event_metadata(
        data["layer1_selections"]
    )

    candidate_mapping = build_candidate_event_mapping(
        data["evaluated_candidates"]
    )

    profiles = []

    for event in data["screenplay_events"]:
        event_id = event["event_id"]
        selections = layer1_metadata.get(event_id, [])

        descriptions = [
            item.get("description", "")
            for item in selections
            if item.get("description")
        ]

        categories = list({
            item["event_category"]
            for item in selections
            if item.get("event_category")
        })

        combined_text = " ".join([
            str(event.get("text") or ""),
            str(event.get("tone") or "")
        ])

        profiles.append({
            "event_id": event_id,
            "episode": event["episode"],
            "scene_number": event["scene_number"],
            "type": event.get("type"),
            "speaker": event.get("speaker"),
            "tone": event.get("tone"),
            "start_time": event.get("start_time"),
            "end_time": event.get("end_time"),
            "text": event.get("text"),
            "keywords": tokenize(combined_text),
            "themes": detect_themes(combined_text),
            "event_categories": categories,
            "layer1_selected": event.get("layer1_selected", False),
            "importance": max(
                [
                    item.get("importance", 0) or 0
                    for item in selections
                ],
                default=0
            ),
            "candidate_ids": candidate_mapping.get(event_id, []),
            "layer1_selections": selections
        })

    return profiles


def identify_frequent_character_names(profiles):
    """
    Identify frequently appearing screenplay speakers.

    Their names are retained as speaker metadata but removed
    from ordinary keyword matching.
    """
    speaker_episode_count = defaultdict(set)

    for profile in profiles:
        speaker = str(profile.get("speaker") or "").strip().lower()

        if speaker:
            speaker_episode_count[speaker].add(profile["episode"])

    frequent_names = set()

    for speaker, episodes in speaker_episode_count.items():
        if len(episodes) >= 3:
            frequent_names.update(tokenize(speaker))

    return frequent_names


def clean_profile_keywords(profiles):
    """Remove frequent character-name tokens from keyword matching."""
    frequent_names = identify_frequent_character_names(profiles)

    for profile in profiles:
        profile["keywords"] -= frequent_names

    return frequent_names


def build_search_index(profiles):
    """Create keyword and theme indexes for efficient discovery."""
    keyword_index = defaultdict(list)
    theme_index = defaultdict(list)

    for profile in profiles:
        for keyword in profile["keywords"]:
            keyword_index[keyword].append(profile["event_id"])

        for theme in profile["themes"]:
            theme_index[theme].append(profile["event_id"])

    return keyword_index, theme_index


def get_episode_number(episode_id):
    match = re.search(r"\d+", str(episode_id))

    if not match:
        return 0

    return int(match.group())


def calculate_episode_diversity_bonus(episode_a, episode_b):
    """
    Small discovery preference for distant episodes.
    This should not dominate thematic compatibility.
    """
    distance = abs(
        get_episode_number(episode_a)
        - get_episode_number(episode_b)
    )

    return min(distance // 10, 3)


def calculate_pair_score(profile_a, profile_b):
    """Calculate preliminary similarity and contrast compatibility."""
    shared_keywords = (
        profile_a["keywords"] & profile_b["keywords"]
    )

    shared_themes = (
        set(profile_a["themes"]) & set(profile_b["themes"])
    )

    shared_categories = (
        set(profile_a["event_categories"])
        & set(profile_b["event_categories"])
    )

    contrast_themes = []

    themes_a = set(profile_a["themes"])
    themes_b = set(profile_b["themes"])

    for contrast in CONTRAST_THEMES:
        theme_one, theme_two = tuple(contrast)

        # A valid contrast requires opposite themes to be
        # present across the two different screenplay events.
        forward_match = (
            theme_one in themes_a and theme_two in themes_b
        )

        reverse_match = (
            theme_two in themes_a and theme_one in themes_b
        )

        if forward_match or reverse_match:
            contrast_themes.append(sorted(contrast))
    score = 0

    # Shared keywords: supporting evidence only.
    keyword_score = min(len(shared_keywords) * 2, 12)
    score += keyword_score

    # Shared themes.
    theme_score = min(len(shared_themes) * 10, 30)
    score += theme_score

    # Contrasting themes.
    contrast_score = min(len(contrast_themes) * 14, 28)
    score += contrast_score

    # Shared Layer 1 categories.
    category_score = min(len(shared_categories) * 6, 12)
    score += category_score

    # Same speaker is useful supporting context, not a major factor.
    speaker_a = str(profile_a.get("speaker") or "").strip().lower()
    speaker_b = str(profile_b.get("speaker") or "").strip().lower()

    same_speaker = bool(
        speaker_a and speaker_b and speaker_a == speaker_b
    )

    if same_speaker:
        score += 3

    diversity_bonus = calculate_episode_diversity_bonus(
        profile_a["episode"],
        profile_b["episode"]
    )

    score += diversity_bonus

    return {
        "score": min(score, 100),
        "keyword_score": keyword_score,
        "theme_score": theme_score,
        "contrast_score": contrast_score,
        "category_score": category_score,
        "episode_diversity_bonus": diversity_bonus,
        "same_speaker": same_speaker,
        "shared_keywords": sorted(shared_keywords),
        "shared_themes": sorted(shared_themes),
        "contrast_themes": contrast_themes,
        "shared_categories": sorted(shared_categories)
    }


def generate_cross_episode_pairs(profiles):
    """Discover promising event pairs across different episodes."""
    profile_lookup = {
        profile["event_id"]: profile
        for profile in profiles
    }

    keyword_index, theme_index = build_search_index(profiles)

    # Store candidate pairs and the reasons they were discovered.
    candidate_pairs = set()

    # 1. Keyword-based discovery.
    for event_ids in keyword_index.values():
        if len(event_ids) > MAX_BUCKET_SIZE:
            continue

        for event_a, event_b in combinations(sorted(event_ids), 2):
            if profile_lookup[event_a]["episode"] != profile_lookup[event_b]["episode"]:
                candidate_pairs.add((event_a, event_b))

    # 2. Shared-theme discovery.
    for event_ids in theme_index.values():
        if len(event_ids) > MAX_BUCKET_SIZE:
            continue

        for event_a, event_b in combinations(sorted(event_ids), 2):
            if profile_lookup[event_a]["episode"] != profile_lookup[event_b]["episode"]:
                candidate_pairs.add((event_a, event_b))

    # 3. Contrast-based discovery.
    for contrast in CONTRAST_THEMES:
        theme_a, theme_b = sorted(contrast)

        events_a = theme_index.get(theme_a, [])
        events_b = theme_index.get(theme_b, [])

        if len(events_a) > MAX_BUCKET_SIZE or len(events_b) > MAX_BUCKET_SIZE:
            continue

        for event_a in events_a:
            for event_b in events_b:
                if event_a == event_b:
                    continue

                if profile_lookup[event_a]["episode"] == profile_lookup[event_b]["episode"]:
                    continue

                candidate_pairs.add(tuple(sorted((event_a, event_b))))

    pair_results = []

    for event_a, event_b in candidate_pairs:
        profile_a = profile_lookup[event_a]
        profile_b = profile_lookup[event_b]

        compatibility = calculate_pair_score(
            profile_a,
            profile_b
        )

        # Do not require shared keywords if theme/contrast evidence exists.
        has_theme_evidence = bool(
            compatibility["shared_themes"]
            or compatibility["contrast_themes"]
        )

        has_keyword_evidence = (
            len(compatibility["shared_keywords"]) >= MIN_SHARED_KEYWORDS
        )

        if not (has_theme_evidence or has_keyword_evidence):
            continue

        if compatibility["score"] < MIN_COMPATIBILITY_SCORE:
            continue

        pair_results.append({
            "event_a": profile_a,
            "event_b": profile_b,
            **compatibility
        })

    pair_results.sort(
        key=lambda item: (
            item["score"],
            item["contrast_score"],
            item["theme_score"],
            item["keyword_score"]
        ),
        reverse=True
    )

    # Limit how often one event appears so results are more diverse.
    neighbor_counts = Counter()
    filtered_pairs = []

    for pair in pair_results:
        event_a_id = pair["event_a"]["event_id"]
        event_b_id = pair["event_b"]["event_id"]

        if (
            neighbor_counts[event_a_id] >= MAX_PAIRS_PER_EVENT
            or neighbor_counts[event_b_id] >= MAX_PAIRS_PER_EVENT
        ):
            continue

        filtered_pairs.append(pair)

        neighbor_counts[event_a_id] += 1
        neighbor_counts[event_b_id] += 1

    return filtered_pairs


def run_compatibility_analysis(data):
    """Build profiles and discover cross-episode combinations."""
    print("Building screenplay event profiles...")

    profiles = build_event_profiles(data)

    frequent_names = clean_profile_keywords(profiles)

    print("Discovering cross-episode event combinations...")

    pairs = generate_cross_episode_pairs(profiles)

    contrast_pair_count = sum(
        bool(pair["contrast_themes"])
        for pair in pairs
    )

    non_adjacent_count = sum(
        abs(
            get_episode_number(pair["event_a"]["episode"])
            - get_episode_number(pair["event_b"]["episode"])
        ) > 1
        for pair in pairs
    )

    return {
        "total_event_profiles": len(profiles),
        "frequent_character_tokens_filtered": sorted(frequent_names),
        "cross_episode_pairs": pairs,
        "total_pairs_discovered": len(pairs),
        "contrast_pairs": contrast_pair_count,
        "non_adjacent_pairs": non_adjacent_count
    }



if __name__ == "__main__":
    from src.promo_composer.candidate_loader import (
        load_promo_composer_data
    )

    data = load_promo_composer_data()
    results = run_compatibility_analysis(data)

    print("\n========== COMPATIBILITY ANALYSIS ==========")
    print(f"Event profiles: {results['total_event_profiles']}")
    print(
        "Frequent character tokens filtered: "
        f"{len(results['frequent_character_tokens_filtered'])}"
    )
    print(f"Cross-episode pairs: {results['total_pairs_discovered']}")
    print(f"Contrast-based pairs: {results['contrast_pairs']}")
    print(f"Non-adjacent episode pairs: {results['non_adjacent_pairs']}")

    print("\nTop 10 discovered pairs:")

    for index, pair in enumerate(
        results["cross_episode_pairs"][:10],
        start=1
    ):
        event_a = pair["event_a"]
        event_b = pair["event_b"]

        print(f"\n{index}. Compatibility score: {pair['score']}")
        print(
            f"   {event_a['event_id']} "
            f"({event_a['episode']})"
        )
        print(
            f"   {event_b['event_id']} "
            f"({event_b['episode']})"
        )
        print(f"   Shared themes: {pair['shared_themes']}")
        print(f"   Contrast themes: {pair['contrast_themes']}")
        print(f"   Shared keywords: {pair['shared_keywords']}")
        print(
            "   Episode diversity bonus: "
            f"{pair['episode_diversity_bonus']}"
        )
        print("   Event A text:")
        print(f"   {event_a.get('text', '')[:300]}")

        print("   Event B text:")
        print(f"   {event_b.get('text', '')[:300]}")

        print("   -------------------------------")