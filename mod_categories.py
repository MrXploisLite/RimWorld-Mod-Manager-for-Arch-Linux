"""
Mod Categories for RimModManager
Auto-categorize mods based on keywords, package IDs, and known patterns.
"""

from enum import Enum
from dataclasses import dataclass
import re


class ModCategory(Enum):
    """Categories for RimWorld mods."""
    FRAMEWORK = "🔧 Framework"
    QOL = "✨ Quality of Life"
    COMBAT = "⚔️ Combat & Weapons"
    ANIMALS = "🐾 Animals & Creatures"
    FACTIONS = "👥 Factions & Races"
    BUILDINGS = "🏠 Buildings & Furniture"
    CRAFTING = "🔨 Crafting & Production"
    MEDICAL = "💊 Medical & Health"
    RESEARCH = "🔬 Research & Technology"
    EVENTS = "📜 Events & Storyteller"
    UI = "🖥️ UI & Interface"
    TEXTURES = "🎨 Textures & Graphics"
    APPAREL = "👕 Apparel & Armor"
    VEHICLES = "🚗 Vehicles"
    MISC = "📦 Miscellaneous"


# Keywords for each category (lowercase)
CATEGORY_KEYWORDS: dict[ModCategory, list[str]] = {
    ModCategory.FRAMEWORK: [
        "harmony", "hugslib", "framework", "library", "lib", "core",
        "patch", "patcher", "loader", "api", "utility", "utils",
        "prerequisite", "dependency", "modbase"
    ],
    ModCategory.QOL: [
        "qol", "quality of life", "tweak", "fix", "improvement",
        "better", "improved", "enhanced", "simple", "easy", "quick",
        "auto", "automatic", "smart", "convenient", "allow", "enable",
        "disable", "toggle", "option", "settings", "config", "menu",
        "stack", "haul", "clean", "organize", "sort", "manage"
    ],
    ModCategory.COMBAT: [
        "combat", "weapon", "gun", "sword", "armor", "shield",
        "melee", "ranged", "turret", "defense", "military", "war",
        "battle", "fight", "attack", "damage", "projectile", "ammo",
        "ammunition", "explosive", "grenade", "missile", "laser",
        "plasma", "ballistic", "ce", "combat extended"
    ],
    ModCategory.ANIMALS: [
        "animal", "creature", "pet", "wildlife", "beast", "monster",
        "dinosaur", "dragon", "insect", "bird", "fish", "dog", "cat",
        "horse", "wolf", "bear", "tame", "hunt", "predator", "prey",
        "livestock", "farm animal", "megafauna", "alpha animal"
    ],
    ModCategory.FACTIONS: [
        "faction", "race", "alien", "species", "tribe", "empire",
        "pirate", "mechanoid", "android", "robot", "humanoid",
        "xenotype", "gene", "biotech", "pawn", "colonist", "npc",
        "trader", "visitor", "enemy", "ally", "rimsenal"
    ],
    ModCategory.BUILDINGS: [
        "building", "furniture", "structure", "wall", "floor", "door",
        "bed", "table", "chair", "storage", "shelf", "container",
        "power", "generator", "battery", "conduit", "light", "lamp",
        "decoration", "decor", "statue", "art", "room", "zone"
    ],
    ModCategory.CRAFTING: [
        "craft", "recipe", "production", "workbench", "forge",
        "smelter", "refinery", "factory", "manufacture", "process",
        "resource", "material", "ingredient", "component", "steel",
        "plasteel", "uranium", "gold", "silver", "jade", "cloth"
    ],
    ModCategory.MEDICAL: [
        "medical", "medicine", "health", "doctor", "surgery",
        "hospital", "disease", "illness", "injury", "wound", "heal",
        "cure", "drug", "pharmaceutical", "prosthetic", "bionic",
        "implant", "organ", "blood", "infection", "epidemic"
    ],
    ModCategory.RESEARCH: [
        "research", "technology", "tech", "science", "study",
        "discover", "unlock", "advance", "progress", "tier",
        "spacer", "glitterworld", "archotech", "mechanitor"
    ],
    ModCategory.EVENTS: [
        "event", "incident", "raid", "quest", "story", "storyteller",
        "scenario", "challenge", "difficulty", "threat", "disaster",
        "weather", "season", "climate", "temperature", "toxic",
        "fallout", "eclipse", "infestation", "manhunter"
    ],
    ModCategory.UI: [
        "ui", "interface", "hud", "menu", "button", "panel",
        "window", "tab", "list", "display", "show", "info",
        "tooltip", "notification", "alert", "message", "log",
        "numbers", "stat", "bar", "indicator", "icon", "label"
    ],
    ModCategory.TEXTURES: [
        "texture", "graphic", "visual", "retexture", "reskin",
        "hd", "high resolution", "sprite", "art style", "aesthetic",
        "color", "theme", "dark", "light", "realistic", "cartoon"
    ],
    ModCategory.APPAREL: [
        "apparel", "clothing", "clothes", "outfit", "wear", "dress",
        "shirt", "pants", "hat", "helmet", "glove", "boot", "cape",
        "robe", "uniform", "fashion", "style", "tribal", "medieval"
    ],
    ModCategory.VEHICLES: [
        "vehicle", "car", "truck", "tank", "mech", "walker",
        "transport", "caravan", "ship", "shuttle", "aircraft",
        "helicopter", "boat", "srts", "giddy-up"
    ],
}

# Known package ID patterns for specific categories
PACKAGE_ID_PATTERNS: dict[str, ModCategory] = {
    r"brrainz\.harmony": ModCategory.FRAMEWORK,
    r"unlimitedhugs\.hugslib": ModCategory.FRAMEWORK,
    r"ludeon\.rimworld": ModCategory.FRAMEWORK,  # Core/DLC
    r".*\.framework": ModCategory.FRAMEWORK,
    r".*\.lib": ModCategory.FRAMEWORK,
    r".*combat.*extended": ModCategory.COMBAT,
    r".*alpha.*animals": ModCategory.ANIMALS,
    r".*vanilla.*expanded": ModCategory.MISC,  # VE has many types
    r".*\.ui\..*": ModCategory.UI,
    r".*\.qol\..*": ModCategory.QOL,
}

# Known mod package IDs with their categories
KNOWN_MODS: dict[str, ModCategory] = {
    # Frameworks
    "brrainz.harmony": ModCategory.FRAMEWORK,
    "unlimitedhugs.hugslib": ModCategory.FRAMEWORK,
    "taranchuk.moderrorchecker": ModCategory.FRAMEWORK,
    "owlchemist.rimthemes": ModCategory.FRAMEWORK,
    
    # Combat
    "ceteam.combatextended": ModCategory.COMBAT,
    "ceteam.combatextended.guns": ModCategory.COMBAT,
    "ceteam.combatextended.melee": ModCategory.COMBAT,
    
    # Animals
    "sarg.alphaanimals": ModCategory.ANIMALS,
    "sarg.alphabiomes": ModCategory.ANIMALS,
    
    # UI
    "fluffy.modmanager": ModCategory.UI,
    "hatti.rimhud": ModCategory.UI,
    "jaxe.bubbles": ModCategory.UI,
    "dubwise.dubsmintmenus": ModCategory.UI,
    "dubwise.dubsmintminimap": ModCategory.UI,
    
    # QoL
    "hatti.allowtool": ModCategory.QOL,
    "jaxe.rimfridge": ModCategory.QOL,
    "fluffy.colonymanager": ModCategory.QOL,
    "fluffy.worktab": ModCategory.QOL,
    "fluffy.animaltab": ModCategory.QOL,
    "fluffy.medicaltab": ModCategory.QOL,
    "fluffy.wildlifetab": ModCategory.QOL,
    "falconne.heatmap": ModCategory.QOL,
    "automatic.recipeicons": ModCategory.QOL,
    "krafs.levelup": ModCategory.QOL,
    "taranchuk.awesomeinventory": ModCategory.QOL,
    
    # Factions
    "erdelf.humanoidalienraces": ModCategory.FACTIONS,
    "oskar.vanillafactionsexpanded.core": ModCategory.FACTIONS,
    
    # Buildings
    "vanillaexpanded.vfecore": ModCategory.BUILDINGS,
    "atlas.androidtiers": ModCategory.FACTIONS,
    
    # Vehicles
    "smashphil.neceros.srtsexpanded": ModCategory.VEHICLES,
    "roolo.giddyupcore": ModCategory.VEHICLES,
}


@dataclass
class CategoryResult:
    """Result of categorization with confidence."""
    category: ModCategory
    confidence: float  # 0.0 to 1.0
    matched_keywords: list[str]


def categorize_mod(
    package_id: str,
    name: str = "",
    description: str = "",
    author: str = ""
) -> CategoryResult:
    """
    Categorize a mod based on its metadata.
    
    Returns CategoryResult with category, confidence, and matched keywords.
    """
    package_id_lower = package_id.lower()
    
    # Check known mods first (highest confidence)
    if package_id_lower in KNOWN_MODS:
        return CategoryResult(
            category=KNOWN_MODS[package_id_lower],
            confidence=1.0,
            matched_keywords=["known_mod"]
        )
    
    # Check package ID patterns
    for pattern, category in PACKAGE_ID_PATTERNS.items():
        if re.match(pattern, package_id_lower):
            return CategoryResult(
                category=category,
                confidence=0.9,
                matched_keywords=[f"pattern:{pattern}"]
            )
    
    # Keyword-based categorization
    searchable_text = " ".join([
        name.lower(),
        description.lower() if description else "",
        package_id_lower,
    ])
    
    # Count keyword matches for each category
    category_scores: dict[ModCategory, tuple[int, list[str]]] = {}
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        matches = []
        for keyword in keywords:
            # Use word boundary matching for better accuracy
            if re.search(rf'\b{re.escape(keyword)}\b', searchable_text):
                matches.append(keyword)
        
        if matches:
            category_scores[category] = (len(matches), matches)
    
    if category_scores:
        # Get category with most matches
        best_category = max(category_scores.keys(), key=lambda c: category_scores[c][0])
        match_count, matched_keywords = category_scores[best_category]
        
        # Calculate confidence based on match count
        confidence = min(0.3 + (match_count * 0.15), 0.85)
        
        return CategoryResult(
            category=best_category,
            confidence=confidence,
            matched_keywords=matched_keywords
        )
    
    # Default to Misc
    return CategoryResult(
        category=ModCategory.MISC,
        confidence=0.1,
        matched_keywords=[]
    )


def get_category_icon(category: ModCategory) -> str:
    """Get just the icon for a category."""
    return category.value.split()[0]


def get_category_name(category: ModCategory) -> str:
    """Get just the name for a category (without icon)."""
    return " ".join(category.value.split()[1:])


def get_all_categories() -> list[ModCategory]:
    """Get all available categories."""
    return list(ModCategory)
