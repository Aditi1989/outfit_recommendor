# enhanced_smartoutfit.py
import datetime
import random
import re
import json
import hashlib
from typing import List, Dict, Tuple
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
import tempfile
import webbrowser
import os

USER_DB = {}

OCCASION_STYLES = {
    "interview": ["formal"],
    "business meeting": ["formal"],
    "office": ["formal", "semi-formal"],
    "office party": ["semi-formal", "party"],
    "office ethnic day": ["ethnic"],
    "college ethnic day": ["ethnic"],
    "ethnic day": ["ethnic"],
    "wedding": [ "party"],
    "ritual": ["ethnic", "traditional"],
    "home ritual": ["ethnic", "traditional"],
    "ceremony": ["ethnic", "formal"],
    "temple visit": ["ethnic", "traditional"],
    "birthday party": ["party"],
    "party": ["party"],
    "casual outing": ["casual", "shopping", "picnic"],
    "picnic": ["casual", "comfortable", "picnic", "shopping"],
    "shopping": ["casual", "shopping", "picnic"],
    "date": ["party", "smart-casual"],
    "beach party": ["party", "summerwear"],
    "kids party": ["colorful", "casual"],
    "kids outing": ["casual", "comfortable"],
    "family outing": ["casual", "semi-formal"],
    "family gathering": ["casual", "ethnic", "semi-formal"],
    "school": ["uniform", "casual"],
    "school function": ["ethnic", "formal"],
    "tuition": ["casual"],
    "cooking": ["comfortable"],
    "swimming": ["swim", "swimwear", "swiming"],
    "sports": ["gym", "yoga", "camping", "trekking", "running","hiking"],
    "gym": ["yoga", "hiking", "camping", "trekking", "running"],
    "exercise": ["gym", "yoga", "hiking", "camping", "trekking", "running"],
    
    "yoga": ["gym", "hiking", "camping", "trekking", "running"],
    "meditation": ["yoga"],
    "hiking": ["gym", "yoga", "camping", "trekking", "running"],
    "camping": ["gym", "yoga", "hiking", "trekking", "running"],
    "trekking": ["gym", "yoga", "camping", "hiking", "running"],
    "mountain climbing": ["gym", "yoga", "camping", "trekking", "running","hiking"],
    "gardening": ["casual","camping"]
}

OCCASION_SYNONYMS = {
    "party": ["birthday party", "beach party", "wedding", "date", "office party", "officeparty"],
    "gym": ["yoga", "hiking", "camping", "trekking", "running", "exercise"],
    "shopping": ["mall", "buying clothes", "store visit"],
    "picnic": ["outdoor fun", "park outing"]
}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username: str, password: str, preferences: Dict = None):
    if username in USER_DB:
        raise ValueError("User already exists")
    USER_DB[username] = {
        "password_hash": hash_password(password),
        "preferences": preferences or {"age_group": "adult", "gender": "unisex"}
    }

def authenticate_user(username: str, password: str) -> bool:
    return username in USER_DB and USER_DB[username]["password_hash"] == hash_password(password)

def get_user_preferences(username: str) -> Dict:
    return USER_DB[username]["preferences"]

def set_user_preferences(username: str, preferences: Dict):
    if username in USER_DB:
        USER_DB[username]["preferences"] = preferences


class SmartOutfitRecommender:
    def __init__(self, wardrobe_path: str):
        with open(wardrobe_path, "r", encoding="utf-8") as f:
            self.wardrobe_db = json.load(f)
        for item in self.wardrobe_db:
            item.setdefault("tags", [])
            item.setdefault("category", "unknown")
            item.setdefault("age_group", "all")
            item.setdefault("gender", "unisex")
            item.setdefault("image", "")

    def get_context(self):
        now = datetime.datetime.now()
        hour = now.hour
        month = now.month
        time_of_day = ("morning" if hour < 12 else "afternoon" if hour < 17 else "evening")
        season = ("winter" if month in [12,1,2] else "summer" if month in [3,4,5] else "monsoon")
        return {"time": time_of_day, "season": season}

    def extract_prompt_requirements(self, prompt: str) -> Tuple[List[str], List[str], List[str], bool]:
        prompt = prompt.lower()
        colors = re.findall(r'\b(?:in|with|wearing|colour|color|shade of)\s+(\w+)', prompt)
        avoid = re.findall(r'\b(?:avoid|not|no|don\'t want|skip)\s+(\w+)', prompt)
        # Normalize forbidden colors to unify near-whites
        avoid = [a.replace("offwhite", "white").replace("off-white", "white").replace("cream", "white").replace("ivory", "white").replace("beige", "white") for a in avoid]

        # Normalize common swim-related misspellings/synonyms
        prompt = prompt.replace("swiming", "swimming").replace("swim ", "swimming ").replace(" swim", " swimming")

        # --- NEW: Normalize office ethnic/traditional/cultural day phrases ---
        office_ethnic_patterns = [
            "office ethnic", "office traditional", "office cultural",
            "office ethnic day", "office traditional day", "office cultural day"
        ]
        # If any of these patterns are present, forcibly add "ethnic day" and "ethnic" to occasions
        force_ethnic = any(pat in prompt for pat in office_ethnic_patterns)

        # --- NEW: If prompt contains "ethnic", "traditional", or "cultural", always force ethnic/traditional ---
        force_ethnic_general = any(word in prompt for word in ["ethnic", "traditional", "cultural"])

        # Extract occasions using regex (as before)
        occasions = re.findall(r'\b(' + '|'.join(re.escape(k) for k in OCCASION_STYLES) + r')\b', prompt)
        # --- Add substring match for any occasion key not already in occasions ---
        for k in OCCASION_STYLES:
            if k not in occasions and k in prompt:
                occasions.append(k)

        # --- Synonym expansion for any matching phrase in prompt ---
        expanded = set(occasions)
        for k, v in OCCASION_SYNONYMS.items():
            for syn in v:
                if syn in prompt:
                    expanded.add(k)
        for occ in occasions:
            for k, v in OCCASION_SYNONYMS.items():
                if occ in v:
                    expanded.add(k)

        # --- NEW: Force ethnic/traditional for office ethnic/traditional/cultural day or if prompt contains those words ---
        if force_ethnic or force_ethnic_general:
            expanded.update(["ethnic day", "ethnic", "traditional"])

        # If still nothing, fallback to "casual" for outing-like prompts
        if not expanded:
            if any(word in prompt for word in ["outing", "walk", "park", "shopping", "picnic"]):
                expanded.add("casual")
        needs_layer = "layer" in prompt or "cold" in prompt
        return list(set(colors)), list(expanded or ["general"]), list(set(avoid)), needs_layer

    def _filter_by_profile(self, items: List[Dict], profile: Dict) -> List[Dict]:
        return [
            item for item in items
            if item["age_group"] in ["all", profile["age_group"]] and item["gender"] in ["unisex", profile["gender"]]
        ]

    def _color_distance(self, color1: str, color2: str) -> float:
        def to_rgb(color):
            css_colors = {"red": (255,0,0), "blue": (0,0,255), "green": (0,128,0), "black": (0,0,0),
                          "white": (255,255,255), "pink": (255,192,203), "gray": (128,128,128),
                          "yellow": (255,255,0), "purple": (128,0,128), "orange": (255,165,0),
                          "brown": (139,69,19), "navy": (0,0,128), "gold": (255,215,0)}
            return css_colors.get(color, (128, 128, 128))

        rgb1 = sRGBColor(*[c / 255 for c in to_rgb(color1)], is_upscaled=False)
        rgb2 = sRGBColor(*[c / 255 for c in to_rgb(color2)], is_upscaled=False)
        lab1 = convert_color(rgb1, LabColor)
        lab2 = convert_color(rgb2, LabColor)
        return delta_e_cie2000(lab1, lab2)

    def _color_match(self, item_tags, requested_colors, forbidden_colors) -> bool:
        # Only consider tags that are color names
        color_terms = {
            "red", "blue", "green", "black", "white", "pink", "gray", "yellow",
            "purple", "orange", "brown", "navy", "gold", "cream", "ivory", "offwhite", "beige"
        }
        color_tags = [tag for tag in item_tags if tag in color_terms]
        # Strictly reject if any tag is close to a forbidden color
        for tag in color_tags:
            if any(self._color_distance(tag, fc) < 15 for fc in forbidden_colors):
                return False
        # If requested colors, require at least one tag close to a requested color
        if requested_colors:
            return any(self._color_distance(tag, rc) < 15 for rc in requested_colors for tag in color_tags)
        # If no requested colors, allow if not forbidden
        return True

    def _filter_items(self, profile, occasions, colors, avoid_colors):
        style_tags = set()
        for occ in occasions:
            style_tags.update(OCCASION_STYLES.get(occ, [occ]))  # fallback to occ as tag
        items = self._filter_by_profile(self.wardrobe_db, profile)
        filtered = [i for i in items if any(tag in i['tags'] for tag in style_tags)]
        # Try color+style filter, but if it yields nothing, fallback to style-only
        if colors:
            color_filtered = [i for i in filtered if self._color_match(i["tags"], colors, avoid_colors)]
            if color_filtered:
                filtered = color_filtered
        return filtered

    def recommend_outfits(self, prompt: str, username: str) -> Dict:
        if username not in USER_DB:
            raise ValueError("User not authenticated")
        profile = get_user_preferences(username)
        colors, occasions, avoid, layer_needed = self.extract_prompt_requirements(prompt)
        context = self.get_context()
        # Ensure layer_needed is set if "layer" or "cold" in prompt or winter season
        layer_needed = layer_needed or ("layer" in prompt or "cold" in prompt or context["season"] == "winter")

        # --- Tag extraction and mapping ---
        style_tags = set()
        for occ in occasions:
            style_tags.update(OCCASION_STYLES.get(occ, [occ]))  # fallback to occ as tag
        style_tags.update(occasions)

        items = self._filter_by_profile(self.wardrobe_db, profile)

        def filter_category(cat, gender=None):
            cat_items = [i for i in items if i["category"] == cat]
            if gender:
                cat_items = [i for i in cat_items if i["gender"] in [gender, "unisex"]]
            return cat_items

        # Color-matched items for each category
        def color_matched(items):
            if colors:
                color_items = [i for i in items if self._color_match(i["tags"], colors, avoid)]
                return color_items if color_items else []
            return []

        gender = profile.get('gender', 'unisex')

        # --- Swimming occasion: ONLY swimwear, color-matched if color specified ---
        if "swimming" in occasions or "swimming" in style_tags:
            swimwear_items = filter_category("swimwear", gender=gender)
            color_matched_swimwear = [i for i in swimwear_items if self._color_match(i["tags"], colors, avoid)] if colors else []
            outfits = [{"type": "swimwear", "items": [sw]} for sw in color_matched_swimwear]
            # Fill up to 3 with other swimwear not already included
            if len(outfits) < 3:
                used_names = {sw["name"] for sw in color_matched_swimwear}
                for sw in swimwear_items:
                    if sw["name"] not in used_names:
                        outfits.append({"type": "swimwear", "items": [sw]})
                        used_names.add(sw["name"])
                    if len(outfits) == 3:
                        break
            while len(outfits) < 3:
                outfits.append({"type": "none", "items": []})
            print("Occasions:", occasions)
            print("Style Tags:", style_tags)
            print("Filtered Swimwear:", [i["name"] for i in swimwear_items])
            return {
                "user": username,
                "occasion": ", ".join(occasions),
                "context": context,
                "outfits": outfits
            }

        # For one-piece, only for females
        one_pieces = filter_category("one-piece", gender="female") + filter_category("one_piece", gender="female") if gender == "female" else []

        # Prioritize tops/bottoms that match style tags (ethnic/traditional etc.)
        tops_all = filter_category("topwear", gender=gender)
        bottoms_all = filter_category("bottomwear", gender=gender)

        # --- Strict style filtering for casual/outing-like prompts ---
        strict_casual_filter = bool(set(style_tags) & {"casual", "comfortable", "picnic", "shopping"})
        if strict_casual_filter:
            tops = [t for t in tops_all if set(t["tags"]) & style_tags]
            bottoms = [b for b in bottoms_all if set(b["tags"]) & style_tags]
        else:
            tops = [t for t in tops_all if any(tag in style_tags for tag in t["tags"])]
            bottoms = [b for b in bottoms_all if any(tag in style_tags for tag in b["tags"])]

        # Only fallback to all if none found
        if not tops:
            tops = tops_all
        if not bottoms:
            bottoms = bottoms_all

        # --- Filter out tops/bottoms with forbidden colors ---
        if avoid:
            tops = [t for t in tops if self._color_match(t["tags"], [], avoid)]
            bottoms = [b for b in bottoms if self._color_match(b["tags"], [], avoid)]

        # --- Ethnic/traditional strict filter for ethnic occasions ---
        if "ethnic" in style_tags or "traditional" in style_tags:
            ethnic_tags = {"ethnic", "traditional"}
            filtered_tops = [t for t in tops if any(tag in ethnic_tags for tag in t["tags"])]
            filtered_bottoms = [b for b in bottoms if any(tag in ethnic_tags for tag in b["tags"])]
            # Only use these if any exist, else fallback to previous
            if filtered_tops:
                tops = filtered_tops
            if filtered_bottoms:
                bottoms = filtered_bottoms

        layers = filter_category("layer", gender=gender)

        print("Occasions:", occasions)
        print("Style Tags:", style_tags)
        filtered = [i for i in items if any(tag in i['tags'] for tag in style_tags)]
        print("Filtered Items:", [i["name"] for i in filtered])
        print("Tops:", [i["name"] for i in tops])
        print("Bottoms:", [i["name"] for i in bottoms])

        # --- Early override for gym/activewear ---
        active_occasions = {"gym", "hiking", "trekking", "yoga", "exercise", "camping"}
        if any(occ in active_occasions for occ in occasions):
            relevant_tops = [t for t in tops if any(tag in style_tags or tag in active_occasions for tag in t["tags"])]
            relevant_bottoms = [b for b in bottoms if any(tag in style_tags or tag in active_occasions for tag in b["tags"])]

            outfits = []
            used_pairs = set()

            # Generate all possible top-bottom pairs (allowing same top with different bottoms)
            all_pairs = []
            for t in relevant_tops:
                for b in relevant_bottoms:
                    all_pairs.append((t, b))

            # Prioritize color-matched pairs if color is specified
            if colors:
                color_pairs = []
                for t, b in all_pairs:
                    if self._color_match(t["tags"], colors, avoid) or self._color_match(b["tags"], colors, avoid):
                        color_pairs.append((t, b))
                pairs_to_use = color_pairs if color_pairs else all_pairs
            else:
                pairs_to_use = all_pairs

            # Fill up to 3 outfits, repeating pairs if needed
            idx = 0
            while len(outfits) < 3:
                t, b = pairs_to_use[idx % len(pairs_to_use)]
                outfits.append({"type": "multi_piece", "items": [t, b]})
                idx += 1

            return {
                "user": username,
                "occasion": ", ".join(occasions),
                "context": context,
                "outfits": outfits[:3]
            }

        # --- Strictly formal for office/business meeting/interview ---
        # Only enforce strict formal wear if NO ethnic/traditional tag is present
        if all(occ in ["office", "business meeting", "interview"] for occ in occasions) and not {"ethnic", "traditional"} & style_tags:


            tops = [t for t in tops if "formal" in t["tags"]]
            bottoms = [b for b in bottoms if "formal" in b["tags"]]
            print("Strictly formal filter applied.")
            print("Formal Tops:", [i["name"] for i in tops])
            print("Formal Bottoms:", [i["name"] for i in bottoms])

        # --- Strictly party for party occasion (including office party) ---
        if "party" in occasions or "office party" in occasions or "beach party" in occasions:
            party_priority_tags = {"party", "semi-formal", "summerwear", "beach party"}
            fallback_tags = {"formal", "office party"}

            party_tops = [t for t in tops if any(tag in party_priority_tags for tag in t["tags"])]
            party_bottoms = [b for b in bottoms if any(tag in party_priority_tags for tag in b["tags"])]

            # If no party-style items, include fallback formal ones
            if not party_tops:
                party_tops = [t for t in tops if any(tag in fallback_tags for tag in t["tags"])]
            if not party_bottoms:
                party_bottoms = [b for b in bottoms if any(tag in fallback_tags for tag in b["tags"])]

            # --- NEW: If still empty and style_tags has ethnic/traditional, fallback to ethnic/traditional filtering ---
            if (not party_tops or not party_bottoms) and ({"ethnic", "traditional"} & style_tags):
                ethnic_tags = {"ethnic", "traditional"}
                party_tops = [t for t in tops_all if any(tag in ethnic_tags for tag in t["tags"])]
                party_bottoms = [b for b in bottoms_all if any(tag in ethnic_tags for tag in b["tags"])]

            # --- Only use color-matched tops/bottoms if color is specified ---
            if colors:
                party_tops_color = [t for t in party_tops if self._color_match(t["tags"], colors, avoid)]
                party_bottoms_color = [b for b in party_bottoms if self._color_match(b["tags"], colors, avoid)]
                if party_tops_color:
                    party_tops = party_tops_color
                if party_bottoms_color:
                    party_bottoms = party_bottoms_color

                # --- For female: prioritize one-piece if available and color-matched ---
                if profile.get("gender") == "female":
                    one_pieces_party = [op for op in one_pieces if any(tag in party_priority_tags for tag in op["tags"])]
                    one_pieces_color = [op for op in one_pieces_party if self._color_match(op["tags"], colors, avoid)]
                    if one_pieces_color:
                        outfits = []
                        # Add up to 3 unique one-piece outfits
                        for op in one_pieces_color[:3]:
                            outfits.append({"type": "one_piece", "items": [op]})
                        # If less than 3, fill with top+bottom combos as before
                        needed = 3 - len(outfits)
                        if party_tops and party_bottoms and needed > 0:
                            top = party_tops[0]
                            unique_bottoms = party_bottoms
                            for i in range(needed):
                                bottom = unique_bottoms[i % len(unique_bottoms)]
                                outfits.append({"type": "multi_piece", "items": [top, bottom]})
                        return {
                            "user": username,
                            "occasion": ", ".join(occasions),
                            "context": context,
                            "outfits": outfits
                        }

                # Always provide 3 full outfits: repeat top with different bottoms if needed, but use different bottoms if possible
                outfits = []
                used_bottoms = set()
                if party_tops and party_bottoms:
                    top = party_tops[0]  # Use the color-matching or prioritized top
                    for b in party_bottoms:
                        if b["name"] not in used_bottoms:
                            combo = [top, b]
                            if layer_needed and layers:
                                combo.append(random.choice(layers))
                            outfits.append({"type": "multi_piece", "items": combo})
                            used_bottoms.add(b["name"])
                            if len(outfits) == 3:
                                break
                    # If not enough outfits, repeat same top with unused bottoms
                    while len(outfits) < 3:
                        b = random.choice(party_bottoms)
                        combo = [top, b]
                        if layer_needed and layers:
                            combo.append(random.choice(layers))
                        outfits.append({"type": "multi_piece", "items": combo})
                # --- NEW: If still no outfits, fallback to ethnic/traditional combos ---
                if not outfits and ({"ethnic", "traditional"} & style_tags):
                    ethnic_tags = {"ethnic", "traditional"}
                    fallback_tops = [t for t in tops_all if any(tag in ethnic_tags for tag in t["tags"])]
                    fallback_bottoms = [b for b in bottoms_all if any(tag in ethnic_tags for tag in b["tags"])]
                    for t, b in zip(fallback_tops, fallback_bottoms):
                        outfits.append({"type": "multi_piece", "items": [t, b]})
                        if len(outfits) == 3:
                            break
                # --- Prevent crash if still empty ---
                if not outfits:
                    return {
                        "user": username,
                        "occasion": ", ".join(occasions),
                        "context": context,
                        "outfits": [{"type": "none", "items": []}] * 3
                    }
                return {
                    "user": username,
                    "occasion": ", ".join(occasions),
                    "context": context,
                    "outfits": outfits
                }

            tops = party_tops
            bottoms = party_bottoms
            print("Prioritized partywear for office party.")

            print("Strictly party filter applied.")
            print("Party Tops:", [i["name"] for i in tops])
            print("Party Bottoms:", [i["name"] for i in bottoms])

        # --- Move color-matched variables here, after all filtering ---
        one_pieces_color = color_matched(one_pieces)
        tops_color = color_matched(tops)
        bottoms_color = color_matched(bottoms)
        layers_color = color_matched(layers)
        print("Color-matched Tops:", [t["name"] for t in tops_color])

        outfits = []
        used = set()

        # --- For females: one-piece outfit if available ---
        strictly_formal = all(occ in ["office", "business meeting", "interview"] for occ in occasions)
        exclude_one_piece_tags = {"ritual", "ceremony", "ethnic", "traditional"}
        exclude_one_piece_casual = {"casual", "comfortable", "picnic", "shopping"}
        if (
            gender == "female"
            and one_pieces
            and not strictly_formal
            and not (exclude_one_piece_tags & style_tags)
            and not (exclude_one_piece_casual & style_tags)
        ):
            op_choices = one_pieces_color if one_pieces_color else one_pieces
            # Only add one one-piece outfit (with layer if needed)
            op = random.choice([o for o in op_choices if o["name"] not in used])
            outfit = [op]
            used.add(op["name"])
            if layer_needed and layers:
                lyr_choices = layers_color if layers_color else layers
                avail_layers = [l for l in lyr_choices if l["name"] not in used]
                if avail_layers:
                    lyr = random.choice(avail_layers)
                    outfit.append(lyr)
                    used.add(lyr["name"])
            outfits.append({"type": "one_piece", "items": outfit})

        # --- Always include at least one top+bottom+layer outfit if layer is needed ---
        if layer_needed and tops and bottoms and layers:
            # Try to avoid duplicates
            tb_pairs = []
            for t in tops:
                for b in bottoms:
                    tb_pairs.append((t, b))
            random.shuffle(tb_pairs)
            added = 0
            for t, b in tb_pairs:
                combo = [t, b]
                lyr_choices = layers_color if layers_color else layers
                avail_layers = [l for l in lyr_choices if l["name"] not in [i["name"] for i in combo]]
                if avail_layers:
                    lyr = random.choice(avail_layers)
                    combo.append(lyr)
                if not any(set(i["name"] for i in combo) == set(j["name"] for j in o["items"]) for o in outfits):
                    outfits.append({"type": "multi_piece", "items": combo})
                    added += 1
                if added >= 2:
                    break

        # --- Always include swimwear for swimming occasion ---
        if "swimming" in occasions or "swimming" in style_tags:
            swimwear_items = filter_category("swimwear", gender=gender)
            for sw in swimwear_items:
                if sw["name"] not in used:
                    outfits.append({"type": "swimwear", "items": [sw]})
                    used.add(sw["name"])
                    if len(outfits) >= 3:
                        break
        else:
            # --- Handle standalone swimwear outfits (legacy logic) ---
            swimwear_items = [i for i in filtered if i["category"] == "swimwear"]
            if swimwear_items:
                for sw in swimwear_items:
                    if sw["name"] not in used:
                        outfits.append({"type": "swimwear", "items": [sw]})
                        used.add(sw["name"])
                        if len(outfits) >= 3:
                            break

        # Adjust how many more outfits we need after adding swimwear
        needed = 3 - len(outfits)

        # --- Top+Bottom outfits ---
        def make_top_bottom_outfits(top_list, bottom_list, layer_list, n, prefer_color=True):
            combos = []
            used_bottoms = set()
            used_pairs = set()

            def maybe_add_layer(combo):
                if layer_needed:
                    lyr_choices = layers_color if layers_color else layer_list
                    avail_layers = [l for l in lyr_choices if l["name"] not in [i["name"] for i in combo]]
                    if avail_layers:
                        filtered_layers = [l for l in avail_layers if any(tag in style_tags for tag in l["tags"])]
                        selected = filtered_layers if filtered_layers else avail_layers
                        lyr = random.choice(selected)
                        combo.append(lyr)

            if prefer_color and (tops_color or bottoms_color):
                for t in tops_color:
                    for b in bottom_list:
                        pair = (t["name"], b["name"])
                        if b["name"] in used_bottoms or pair in used_pairs:
                            continue
                        if not (self._color_match(t["tags"], colors, []) or self._color_match(b["tags"], colors, [])):
                            continue
                        combo = [t, b]
                        used_bottoms.add(b["name"])
                        used_pairs.add(pair)
                        maybe_add_layer(combo)
                        combos.append({"type": "multi_piece", "items": combo})
                        if len(combos) >= n:
                            return combos

                for b in bottoms_color:
                    if b["name"] in used_bottoms:
                        continue
                    for t in top_list:
                        pair = (t["name"], b["name"])
                        if pair in used_pairs:
                            continue
                        if not (self._color_match(t["tags"], colors, []) or self._color_match(b["tags"], colors, [])):
                            continue
                        combo = [t, b]
                        used_bottoms.add(b["name"])
                        used_pairs.add(pair)
                        maybe_add_layer(combo)
                        combos.append({"type": "multi_piece", "items": combo})
                        if len(combos) >= n:
                            return combos

            if colors and len(tops_color) == 1:
                top = tops_color[0]
                bottom_used = set()
                for b in bottoms_color + bottom_list:
                    if b["name"] in bottom_used:
                        continue
                    pair = (top["name"], b["name"])
                    if pair in used_pairs:
                        continue
                    combo = [top, b]
                    used_pairs.add(pair)
                    bottom_used.add(b["name"])
                    maybe_add_layer(combo)
                    combos.append({"type": "multi_piece", "items": combo})
                    if len(combos) >= n - 1:
                        break
                for t in top_list:
                    for b in bottom_list:
                        pair = (t["name"], b["name"])
                        if pair in used_pairs or t["name"] == top["name"]:
                            continue
                        if self._color_match(t["tags"], colors, []):
                            continue
                        combo = [t, b]
                        maybe_add_layer(combo)
                        combos.append({"type": "multi_piece", "items": combo})
                        return combos[:n]
                return combos[:n]

            if not colors:
                used_tops = set()
                used_bottoms = set()
                for t in top_list:
                    for b in bottom_list:
                        pair = (t["name"], b["name"])
                        if t["name"] in used_tops or b["name"] in used_bottoms or pair in used_pairs:
                            continue
                        combo = [t, b]
                        used_tops.add(t["name"])
                        used_bottoms.add(b["name"])
                        used_pairs.add(pair)
                        maybe_add_layer(combo)
                        combos.append({"type": "multi_piece", "items": combo})
                        if len(combos) >= n:
                            return combos
                for t in top_list:
                    for b in bottom_list:
                        pair = (t["name"], b["name"])
                        if pair in used_pairs:
                            continue
                        combo = [t, b]
                        maybe_add_layer(combo)
                        combos.append({"type": "multi_piece", "items": combo})
                        if len(combos) >= n:
                            return combos
                return combos

            for t in top_list:
                for b in bottom_list:
                    pair = (t["name"], b["name"])
                    if b["name"] in used_bottoms or pair in used_pairs:
                        continue
                    if colors and (self._color_match(t["tags"], colors, []) or self._color_match(b["tags"], colors, [])):
                        continue
                    combo = [t, b]
                    used_bottoms.add(b["name"])
                    used_pairs.add(pair)
                    maybe_add_layer(combo)
                    combos.append({"type": "multi_piece", "items": combo})
                    if len(combos) >= n:
                        return combos
            return combos


        # How many more outfits needed?
        needed = 3 - len(outfits)
        # Try to fill with color-matched first, then fallback to occasion-matched
        combos = make_top_bottom_outfits(tops, bottoms, layers, needed, prefer_color=True)
        outfits.extend(combos)
        needed = 3 - len(outfits)
        if needed > 0:
            combos = make_top_bottom_outfits(tops, bottoms, layers, needed, prefer_color=False)
            outfits.extend(combos)

        # --- Ensure no 'none' outfits are returned ---
        if len(outfits) < 3:
            # Attempt to reuse tops with different bottoms
            used_pairs = set(
                (item["name"] for item in outfit["items"] if item["category"] in ["topwear", "bottomwear"])
                for outfit in outfits
            )
            extra_outfits = []
            for t in tops:
                for b in bottoms:
                    pair = (t["name"], b["name"])
                    if pair not in used_pairs:
                        combo = [t, b]
                        # Add layer if needed
                        if layer_needed and layers:
                            lyr = random.choice(layers)
                            combo.append(lyr)
                        extra_outfits.append({"type": "multi_piece", "items": combo})
                        used_pairs.add(pair)
                        if len(outfits) + len(extra_outfits) >= 3:
                            break
                if len(outfits) + len(extra_outfits) >= 3:
                    break
            outfits.extend(extra_outfits[:3 - len(outfits)])

        # Final fallback: if still not 3, reuse existing outfits with different bottoms
        while len(outfits) < 3:
            t = random.choice(tops)
            b = random.choice(bottoms)
            combo = [t, b]
            if layer_needed and layers:
                combo.append(random.choice(layers))
            outfits.append({"type": "multi_piece", "items": combo})

        # --- Special handling for active/sport occasions ---
        active_occasions = {"gym", "hiking", "trekking", "yoga", "exercise", "camping"}
        if any(occ in active_occasions for occ in occasions):
            used_top = set()
            used_bottom = set()
            # Only use tops/bottoms that match style tags for these occasions
            relevant_tops = [t for t in tops if any(tag in active_occasions or tag in style_tags for tag in t["tags"])]
            relevant_bottoms = [b for b in bottoms if any(tag in active_occasions or tag in style_tags for tag in b["tags"])]
            # Prioritize color-matched items
            tops_color = [t for t in relevant_tops if self._color_match(t["tags"], colors, avoid)]
            bottoms_color = [b for b in relevant_bottoms if self._color_match(b["tags"], colors, avoid)]
            top_priority = tops_color + [t for t in relevant_tops if t["name"] not in [i["name"] for i in tops_color]]
            bottom_priority = bottoms_color + [b for b in relevant_bottoms if b["name"] not in [i["name"] for i in bottoms_color]]

            # First: Add color-matched combo
            for t in top_priority:
                for b in bottom_priority:
                    if self._color_match(t["tags"], colors, avoid) or self._color_match(b["tags"], colors, avoid):
                        if t["name"] not in used_top and b["name"] not in used_bottom:
                            outfits.append({"type": "multi_piece", "items": [t, b]})
                            used_top.add(t["name"])
                            used_bottom.add(b["name"])
                            break
                if len(outfits) >= 1:
                    break

            # Second: Add 2 more from style-matching (no color priority)
            for t in relevant_tops:
                for b in relevant_bottoms:
                    if t["name"] not in used_top and b["name"] not in used_bottom:
                        outfits.append({"type": "multi_piece", "items": [t, b]})
                        used_top.add(t["name"])
                        used_bottom.add(b["name"])
                        if len(outfits) >= 3:
                            break
                if len(outfits) >= 3:
                    break

            # Final fallback: fill if < 3
            while len(outfits) < 3:
                outfits.append({"type": "none", "items": []})

            return {
                "user": username,
                "occasion": ", ".join(occasions),
                "context": context,
                "outfits": outfits[:3]
            }

        return {
            "user": username,
            "occasion": ", ".join(occasions),
            "context": context,
            "outfits": outfits[:3]
        }
def show_outfits_html(result):
    html = """
    <html>
    <head>
        <title>Recommended Outfits</title>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .outfit {{ margin-bottom: 30px; }}
            .item {{ margin-left: 20px; }}
            img {{ max-width: 200px; max-height: 200px; display: block; margin-top: 5px; }}
        </style>
    </head>
    <body>
        <h2>Recommended Outfits for {user}</h2>
        <p><b>Occasion:</b> {occasion}</p>
        <p><b>Context:</b> {context}</p>
    """.format(
        user=result['user'],
        occasion=result['occasion'],
        context=", ".join(f"{k}: {v}" for k, v in result['context'].items())
    )
    for idx, outfit in enumerate(result['outfits'], 1):
        html += f'<div class="outfit"><h3>Outfit {idx} ({outfit["type"]})</h3>'
        for item in outfit['items']:
            html += f'<div class="item"><b>{item["name"]} ({item["category"]})</b><br>'
            img_path = item.get("image", "")
            if img_path and os.path.exists(img_path):
                html += f'<img src="file:///{os.path.abspath(img_path)}">'
            elif img_path:
                html += f'<img src="{img_path}">'
            else:
                html += '<i>No image available</i>'
            html += '</div>'
        html += '</div>'
    html += "</body></html>"

    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
        f.write(html)
        temp_html_path = f.name
    webbrowser.open('file://' + os.path.abspath(temp_html_path))

def show_all_outfits(wardrobe_path):
    with open(wardrobe_path, "r", encoding="utf-8") as f:
        wardrobe = json.load(f)
    html = """
    <html>
    <head>
        <title>All Outfits</title>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .item {{ margin-bottom: 20px; }}
            img {{ max-width: 200px; max-height: 200px; display: block; margin-top: 5px; }}
        </style>
    </head>
    <body>
        <h2>All Outfits in Wardrobe</h2>
    """
    for item in wardrobe:
        html += f'<div class="item"><b>{item["name"]} ({item["category"]})</b><br>'
        img_path = item.get("image", "")
        if img_path and os.path.exists(img_path):
            html += f'<img src="file:///{os.path.abspath(img_path)}">'
        elif img_path:
            html += f'<img src="{img_path}">'
        else:
            html += '<i>No image available</i>'
        html += '</div>'
    html += "</body></html>"

    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
        f.write(html)
        temp_html_path = f.name
    webbrowser.open('file://' + os.path.abspath(temp_html_path))

# --- Interactive Terminal Entry ---
if __name__ == "__main__":
    print("Welcome to the Smart Outfit Recommender")
    print("1. Show all outfits in wardrobe")
    print("2. Get outfit recommendations")
    choice = input("Enter your choice (1/2): ").strip()
    if choice == "1":
        show_all_outfits("wardrobe.json")
        exit()
    username = input("Enter your name: ").strip().lower()
    password = input("Set or enter your password: ").strip()

    if username not in USER_DB:
        age_group = input("Enter your age group (toddler/teen/adult/senior): ").strip().lower()
        gender = input("Enter your gender (male/female/unisex): ").strip().lower()
        register_user(username, password, {"age_group": age_group, "gender": gender})
    else:
        if not authenticate_user(username, password):
            print("Invalid password. Exiting.")
            exit()

    recommender = SmartOutfitRecommender("wardrobe.json")
    while True:
        print("\nAvailable occasions include:")
        print(", ".join(sorted(OCCASION_STYLES.keys())))
        print("Please select an occasion from the above list.")
        occasion_input = input("Occasion (or type 'exit' to quit): ").strip()
        if occasion_input.lower() == "exit":
            print("Goodbye!")
            break
        # Optionally, allow user to add more details (color, avoid, etc.)
        extra_prompt = input("Any specific preferences? (e.g. color, avoid, layering) If none, press Enter: ").strip()
        if extra_prompt:
            prompt = f"{occasion_input} {extra_prompt}"
        else:
            prompt = occasion_input
        result = recommender.recommend_outfits(prompt, username)
        print("\nRecommended Outfits:")
        for idx, outfit in enumerate(result['outfits'], 1):
            print(f"\nOutfit {idx} ({outfit['type']}):")
            for item in outfit['items']:
                print(f"  - {item['name']} ({item['category']})")
                print(f"    Image: {item.get('image', 'No image available')}")
        # Show HTML popup with images
        show_outfits_html(result)

