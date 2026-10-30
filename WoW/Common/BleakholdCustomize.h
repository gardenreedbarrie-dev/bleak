#ifndef WOW_COMMON_BLEAKHOLDCUSTOMIZE_H
#define WOW_COMMON_BLEAKHOLDCUSTOMIZE_H

#include <cstdint>

// BLEAKHOLD(customize): a model, free of the client core, of the option walks the customization arrows make.
// The stock arrows (CCharacterCreation::CycleCharCustomization on the creation and customize screens,
// CGBarberShop::SetNextBarberShopStyle at the barber) step through CharacterComponent.cpp's SetNext*/SetPrev*,
// which skip values whose CharSections rows do not fit. Nothing in 3.3.5a tells the UI where it stands in that
// walk, so the picker's "n/N" labels, its jumps and its per-row randomize need the same walk as data:
//   List      the values one row's arrows reach from the current look, in walk order (ascending);
//   Info      the 1-based position of the current value in that list (0 when it is off the list), the count and
//             the raw value;
//   PlanJump  the setter calls one arrow press makes when it lands on a given value, including its side effects
//             (a face can bring its own skin, a hair style or a features value can bring a hair colour, and a
//             hair style that changes the hair colour resets the features to the first one).
// Every predicate below is a line-by-line copy of the CharacterComponent.cpp function named next to it; keep them
// in step. Tools/CustomizeWalk/tests/test_customize_walk.cpp checks each list and jump against a transliteration
// of those functions on generated tables. The client feeds the model from the live tables through
// WoW/Source/Glue/BleakholdCustomizeTable.h.
//
// Table concept (T):
//   int32_t NumVariations(int32_t section) const;            ComponentGetNumVariations
//   int32_t NumColors(int32_t section, int32_t variation) const;   ComponentGetNumColors
//   Cell    Get(int32_t section, int32_t variation, int32_t color) const;   ComponentGetSectionsRecord: inRange is
//           its "found", present that it returned a row, flags that row's flags
//   bool    Match(uint32_t flags) const;                     ComponentFlagsMatch with the screen's selection
//   int32_t FacialStyles() const;                            CharacterFacialHairStyles rows of the race and sex
//   bool    AnyUnderwear() const;                            COMPONENT_CONTEXT_2: underwear rows are not checked
//   bool    NpcSkin() const;                                 ComponentData flag 0x1: SetFace changes nothing
namespace BleakholdCustomize {

// Rows as CycleCharCustomization numbers them (the Lua row is Row + 1, keep masks use bit Row).
enum Row : int32_t {
    ROW_SKIN = 0,
    ROW_FACE = 1,
    ROW_HAIR_STYLE = 2,
    ROW_HAIR_COLOR = 3,
    ROW_FEATURES = 4,
    NUM_ROWS = 5,
};

// CharSections base sections (COMPONENT_VARIATIONS).
enum Section : int32_t {
    SEC_SKIN = 0,
    SEC_FACE = 1,
    SEC_FACIAL_HAIR = 2,
    SEC_HAIR = 3,
    SEC_UNDERWEAR = 4,
};

// Values are bytes on the wire, so no row has more than this many values a player can store.
static const int32_t MAX_VALUES = 256;

struct Prefs {
    int32_t skin;
    int32_t face;
    int32_t hairStyle;
    int32_t hairColor;
    int32_t facial;
};

struct Cell {
    bool inRange;
    bool present;
    uint32_t flags;
};

// The CCharacterComponent setter a plan step calls.
enum OpKind : int32_t {
    OP_SKIN = 0,        // SetSkinColor(value, load, true, nullptr)
    OP_FACE = 1,        // SetFace(value, true, nullptr)
    OP_HAIR_COLOR = 2,  // SetHairColor(value, load, nullptr)
    OP_HAIR_STYLE = 3,  // SetHairStyle(value, nullptr)
    OP_BEARD = 4,       // SetBeardStyle(value, true, nullptr)
};

struct Op {
    int32_t kind;
    int32_t value;
    bool load;
};

struct Plan {
    int32_t count;
    Op ops[4];
    Prefs result;  // the look after the ops, as the setters' own checks leave it
};

struct Info {
    int32_t position;  // 1-based place of raw in the walk, 0 when the arrows cannot come back to it
    int32_t count;     // values the arrows reach
    int32_t raw;       // the row's value (the byte the server stores)
};

inline int32_t RowValue(const Prefs& p, int32_t row) {
    switch (row) {
        case ROW_SKIN: return p.skin;
        case ROW_FACE: return p.face;
        case ROW_HAIR_STYLE: return p.hairStyle;
        case ROW_HAIR_COLOR: return p.hairColor;
        case ROW_FEATURES: return p.facial;
        default: return -1;
    }
}

template <class T>
inline bool Ok(const T& t, int32_t section, int32_t variation, int32_t color) {
    Cell c = t.Get(section, variation, color);
    return c.present && t.Match(c.flags);
}

// SetNextSkin / SetPrevSkin: the skin, the current face on it and its underwear must all fit.
template <class T>
inline bool SkinFits(const T& t, const Prefs& p, int32_t skin) {
    return Ok(t, SEC_SKIN, 0, skin) && Ok(t, SEC_FACE, p.face, skin) && (t.AnyUnderwear() || Ok(t, SEC_UNDERWEAR, 0, skin));
}

// SetNextFace / SetPrevFace: a face fits when one of the skins its odd inner loop visits (starting at colorOffset,
// the glue's last chosen skin) fits with it; *skinOut is that skin, which the step takes when the current one
// does not fit the face.
template <class T>
inline bool FaceFits(const T& t, int32_t face, int32_t colorOffset, int32_t* skinOut) {
    int32_t numColors = t.NumColors(SEC_FACE, face);
    int32_t skinID = 0;

    // the stock loop ends within numColors turns (it stops at skin numColors - 1); the guard only bounds bad input
    for (int32_t i = 0, guard = 0; i < numColors && guard <= numColors; i = skinID + 1, guard++) {
        skinID = (i + colorOffset) % numColors;

        if (Ok(t, SEC_FACE, face, skinID) && Ok(t, SEC_SKIN, 0, skinID) && (t.AnyUnderwear() || Ok(t, SEC_UNDERWEAR, 0, skinID))) {
            if (skinOut) {
                *skinOut = skinID;
            }

            return true;
        }
    }

    return false;
}

// SetNextHairStyle / SetPrevHairStyle: a style fits when any of its colours fits; *colorOut is the first.
template <class T>
inline bool StyleFits(const T& t, int32_t style, int32_t* colorOut) {
    int32_t numColors = t.NumColors(SEC_HAIR, style);

    for (int32_t color = 0; color < numColors; color++) {
        if (Ok(t, SEC_HAIR, style, color)) {
            if (colorOut) {
                *colorOut = color;
            }

            return true;
        }
    }

    return false;
}

// SetNextFacialFeature / SetPrevFacialFeature (row branch): a value fits when any hair colour of it fits.
template <class T>
inline bool FeatureFits(const T& t, int32_t facial, int32_t* colorOut) {
    int32_t numColors = t.NumColors(SEC_FACIAL_HAIR, facial);

    for (int32_t color = 0; color < numColors; color++) {
        if (Ok(t, SEC_FACIAL_HAIR, facial, color)) {
            if (colorOut) {
                *colorOut = color;
            }

            return true;
        }
    }

    return false;
}

// SetNextFacialFeature's "found": with CharSections rows at the current value and hair colour, features walk the
// rows; otherwise they count through CharacterFacialHairStyles with no checks.
template <class T>
inline bool FeaturesByRows(const T& t, const Prefs& p) {
    return t.Get(SEC_FACIAL_HAIR, p.facial, p.hairColor).inRange;
}

// GetNumFacialFeaturesForHairColor
template <class T>
inline int32_t NumFeaturesAtColor(const T& t, int32_t hairColor) {
    int32_t numVariations = t.NumVariations(SEC_FACIAL_HAIR);

    if (!numVariations) {
        return t.FacialStyles();
    }

    int32_t count = 0;

    for (int32_t i = 0; i < numVariations; i++) {
        if (Ok(t, SEC_FACIAL_HAIR, i, hairColor)) {
            count++;
        }
    }

    return count;
}

// GetNthFacialFeatureIndex (it walks only the first "count" variations, as the stock code does)
template <class T>
inline int32_t NthFeature(const T& t, const Prefs& p, int32_t index) {
    if (!t.Get(SEC_FACIAL_HAIR, p.facial, p.hairColor).inRange) {
        return index < t.FacialStyles() ? index : -1;
    }

    int32_t count = NumFeaturesAtColor(t, p.hairColor);

    if (count <= 0) {
        return -1;
    }

    int32_t matched = 0;

    for (int32_t i = 0; i < count; i++) {
        if (Ok(t, SEC_FACIAL_HAIR, i, p.hairColor)) {
            if (index == matched) {
                return i;
            }

            matched++;
        }
    }

    return -1;
}

// ComponentValidateFacialFeature: whether features value p.facial is valid at hair colour hairColor.
template <class T>
inline bool FeatureValidAt(const T& t, const Prefs& p, int32_t hairColor) {
    if (p.facial < 0 || p.facial > t.FacialStyles()) {
        return false;
    }

    int32_t numVariations = t.NumVariations(SEC_FACIAL_HAIR);

    if (p.facial >= numVariations || !numVariations || hairColor < 0) {
        return true;
    }

    int32_t numColors = t.NumColors(SEC_FACIAL_HAIR, p.facial);

    if (hairColor >= numColors || !numColors) {
        return true;
    }

    Cell c = t.Get(SEC_FACIAL_HAIR, p.facial, hairColor);
    return c.present && t.Match(c.flags);
}

// The values of a row's walk the arrows can land on, ascending. The walk visits them in this order forwards
// (wrapping) and in reverse backwards. Fills at most cap values and returns how many there are.
template <class T>
inline int32_t List(const T& t, const Prefs& p, int32_t row, int32_t colorOffset, int32_t* values, int32_t cap) {
    int32_t count = 0;
    int32_t domain = 0;

    switch (row) {
        case ROW_SKIN: domain = t.NumColors(SEC_SKIN, 0); break;
        case ROW_FACE: domain = t.NumVariations(SEC_FACE); break;
        case ROW_HAIR_STYLE: domain = t.NumVariations(SEC_HAIR); break;
        case ROW_HAIR_COLOR: domain = t.NumColors(SEC_HAIR, p.hairStyle); break;
        case ROW_FEATURES: domain = FeaturesByRows(t, p) ? t.NumVariations(SEC_FACIAL_HAIR) : t.FacialStyles(); break;
        default: return 0;
    }

    bool byRows = row == ROW_FEATURES && FeaturesByRows(t, p);

    for (int32_t v = 0; v < domain; v++) {
        bool fits;

        switch (row) {
            case ROW_SKIN: fits = SkinFits(t, p, v); break;
            case ROW_FACE: fits = FaceFits(t, v, colorOffset, nullptr); break;
            case ROW_HAIR_STYLE: fits = StyleFits(t, v, nullptr); break;
            case ROW_HAIR_COLOR: fits = Ok(t, SEC_HAIR, p.hairStyle, v); break;
            default: fits = byRows ? FeatureFits(t, v, nullptr) : true; break;
        }

        if (fits) {
            if (values && count < cap) {
                values[count] = v;
            }

            count++;
        }
    }

    return count;
}

inline Info InfoFromList(const int32_t* values, int32_t count, int32_t cap, int32_t raw) {
    Info info = { 0, count, raw };
    int32_t stored = count < cap ? count : cap;

    for (int32_t i = 0; i < stored; i++) {
        if (values[i] == raw) {
            info.position = i + 1;
            break;
        }
    }

    return info;
}

template <class T>
inline Info RowInfo(const T& t, const Prefs& p, int32_t row, int32_t colorOffset) {
    int32_t values[MAX_VALUES];
    int32_t count = List(t, p, row, colorOffset, values, MAX_VALUES);
    return InfoFromList(values, count, MAX_VALUES, RowValue(p, row));
}

// Keeps the listed values for which keep(value) holds, in order; returns the new count.
template <class F>
inline int32_t Filter(int32_t* values, int32_t count, int32_t cap, F keep) {
    int32_t stored = count < cap ? count : cap;
    int32_t kept = 0;

    for (int32_t i = 0; i < stored; i++) {
        if (keep(values[i])) {
            values[kept++] = values[i];
        }
    }

    return kept;
}

inline bool InList(const int32_t* values, int32_t count, int32_t cap, int32_t value) {
    int32_t stored = count < cap ? count : cap;

    for (int32_t i = 0; i < stored; i++) {
        if (values[i] == value) {
            return true;
        }
    }

    return false;
}

// Where one arrow press goes from current in an ascending list: the next value up (or down), wrapping; false when
// the press would not move (the stock step returns false).
inline bool Neighbour(const int32_t* values, int32_t count, int32_t cap, int32_t current, bool forward, int32_t* out) {
    int32_t stored = count < cap ? count : cap;

    if (stored <= 0) {
        return false;
    }

    int32_t pick = forward ? values[0] : values[stored - 1];

    if (forward) {
        for (int32_t i = 0; i < stored; i++) {
            if (values[i] > current) {
                pick = values[i];
                break;
            }
        }
    } else {
        for (int32_t i = stored - 1; i >= 0; i--) {
            if (values[i] < current) {
                pick = values[i];
                break;
            }
        }
    }

    if (pick == current) {
        return false;
    }

    *out = pick;
    return true;
}

// What each setter leaves in the look, with its own checks (SetSkinColor, SetFace, SetHairColor, SetHairStyle,
// SetBeardStyle).
template <class T>
inline void Simulate(const T& t, Prefs& p, const Op& op) {
    switch (op.kind) {
        case OP_SKIN:
            p.skin = op.value;
            break;

        case OP_FACE: {
            if (t.NpcSkin()) {
                break;
            }

            Cell skin = t.Get(SEC_SKIN, 0, p.skin);

            if (skin.present && (skin.flags & 0x8)) {
                break;
            }

            if (t.Get(SEC_FACE, op.value, p.skin).inRange) {
                p.face = op.value;
            }

            break;
        }

        case OP_HAIR_COLOR:
            if (t.Get(SEC_HAIR, p.hairStyle, op.value).inRange) {
                p.hairColor = op.value;
            }

            break;

        case OP_HAIR_STYLE:
            if (t.Get(SEC_HAIR, op.value, p.hairColor).inRange) {
                p.hairStyle = op.value;
            }

            break;

        case OP_BEARD:
            if (op.value >= 0 && op.value <= t.FacialStyles()) {
                p.facial = op.value;
            }

            break;

        default:
            break;
    }
}

template <class T>
inline void PlanAdd(const T& t, Plan* plan, int32_t kind, int32_t value, bool load) {
    Op& op = plan->ops[plan->count++];
    op.kind = kind;
    op.value = value;
    op.load = load;
    Simulate(t, plan->result, op);
}

// The setter calls of one arrow press on row whose walk picks value (the end of SetNext*/SetPrev*); false when value
// is not on the row's list.
template <class T>
inline bool PlanStep(const T& t, const Prefs& p, int32_t row, int32_t value, int32_t colorOffset, Plan* plan) {
    int32_t values[MAX_VALUES];
    int32_t count = List(t, p, row, colorOffset, values, MAX_VALUES);

    if (!InList(values, count, MAX_VALUES, value)) {
        return false;
    }

    plan->count = 0;
    plan->result = p;

    switch (row) {
        case ROW_SKIN:
            PlanAdd(t, plan, OP_SKIN, value, true);
            return true;

        case ROW_FACE: {
            int32_t skinID = p.skin;
            FaceFits(t, value, colorOffset, &skinID);

            if (!SkinFits(t, Prefs{ p.skin, value, p.hairStyle, p.hairColor, p.facial }, p.skin)) {
                PlanAdd(t, plan, OP_SKIN, skinID, false);
            }

            PlanAdd(t, plan, OP_FACE, value, true);
            return true;
        }

        case ROW_HAIR_STYLE: {
            if (Ok(t, SEC_HAIR, value, p.hairColor)) {
                PlanAdd(t, plan, OP_HAIR_STYLE, value, false);
                return true;
            }

            int32_t color = 0;
            StyleFits(t, value, &color);
            PlanAdd(t, plan, OP_HAIR_COLOR, color, true);
            PlanAdd(t, plan, OP_HAIR_STYLE, value, false);
            int32_t facial = NthFeature(t, plan->result, 0);

            if (facial >= 0) {
                PlanAdd(t, plan, OP_BEARD, facial, true);
            }

            return true;
        }

        case ROW_HAIR_COLOR:
            PlanAdd(t, plan, OP_HAIR_COLOR, value, true);
            return true;

        case ROW_FEATURES: {
            if (FeaturesByRows(t, p) && !Ok(t, SEC_FACIAL_HAIR, value, p.hairColor)) {
                int32_t color = 0;
                FeatureFits(t, value, &color);
                PlanAdd(t, plan, OP_HAIR_COLOR, color, false);
            }

            PlanAdd(t, plan, OP_BEARD, value, true);
            return true;
        }

        default:
            return false;
    }
}

// PlanStep for a jump: false, and no plan, when value is not on the row's list, or when the setters' own checks would
// leave the row short of it (a hair style whose first colour the current style does not have, for example: the
// stock press does not get there either).
template <class T>
inline bool PlanJump(const T& t, const Prefs& p, int32_t row, int32_t value, int32_t colorOffset, Plan* plan) {
    return PlanStep(t, p, row, value, colorOffset, plan) && RowValue(plan->result, row) == value;
}

// Randomize with locked rows: the skins that fit a kept face (the skin walk), and the hair colours of the current
// style at which a kept features value stays valid.
template <class T>
inline int32_t KeepFaceSkins(const T& t, const Prefs& p, int32_t* values, int32_t cap) {
    return List(t, p, ROW_SKIN, 0, values, cap);
}

template <class T>
inline int32_t KeepFeatureColors(const T& t, const Prefs& p, int32_t* values, int32_t cap) {
    int32_t count = 0;
    int32_t numColors = t.NumColors(SEC_HAIR, p.hairStyle);

    for (int32_t color = 0; color < numColors; color++) {
        if (Ok(t, SEC_HAIR, p.hairStyle, color) && FeatureValidAt(t, p, color)) {
            if (values && count < cap) {
                values[count] = color;
            }

            count++;
        }
    }

    return count;
}

// RandomizeCharCustomization(keepMask): the stock order (skin, face, hair colour, hair style, features) with the
// kept rows left out. A rolled skin must fit a kept face, and a rolled hair colour must keep a kept features value
// valid; every other row uses the stock random picker, which already fits the rows rolled before it. keepMask 0 is
// the stock sequence. R provides: Prefs Look() const; int32_t Dice(int32_t n) (0 .. n - 1, CRandom::dice_);
// RandomSkin(), RandomFace(), RandomHairColor(), RandomHairStyle(), RandomFeatures() (the SetRandom* functions);
// SetSkin(v) (SetSkinColor(v, true, true)) and SetHairColor(v) (SetHairColor(v, true)).
template <class R, class T>
inline void RandomizeKeep(R& r, const T& t, uint32_t keepMask) {
    int32_t values[MAX_VALUES];

    if (!(keepMask & (1u << ROW_SKIN))) {
        if (keepMask & (1u << ROW_FACE)) {
            int32_t count = KeepFaceSkins(t, r.Look(), values, MAX_VALUES);
            count = count < MAX_VALUES ? count : MAX_VALUES;

            if (count > 0) {
                r.SetSkin(values[r.Dice(count)]);
            }
        } else {
            r.RandomSkin();
        }
    }

    if (!(keepMask & (1u << ROW_FACE))) {
        r.RandomFace();
    }

    if (!(keepMask & (1u << ROW_HAIR_COLOR))) {
        if (keepMask & (1u << ROW_FEATURES)) {
            int32_t count = KeepFeatureColors(t, r.Look(), values, MAX_VALUES);
            count = count < MAX_VALUES ? count : MAX_VALUES;

            if (count > 0) {
                r.SetHairColor(values[r.Dice(count)]);
            }
        } else {
            r.RandomHairColor();
        }
    }

    if (!(keepMask & (1u << ROW_HAIR_STYLE))) {
        r.RandomHairStyle();
    }

    if (!(keepMask & (1u << ROW_FEATURES))) {
        r.RandomFeatures();
    }
}

// The barbershop's skin arrows: step with the stock SetNextSkin / SetPrevSkin until the skin has a BarberShopStyle
// row, or the walk is back where it started (so it never stops on a skin the barber cannot sell, which left
// m_currentSkinColor null and crashed in GetTotalCost). On complete tables the first step has a row and this is the
// stock single step. When the start is off the walk (its face does not fit it) and no skin on the walk has a row,
// the walk never comes back: it goes back to the start with Set. S provides: bool Step(bool forward);
// int32_t Value() const; bool HasRow(int32_t value) const; void Set(int32_t value) (SetSkinColor(value, true, true)).
template <class S>
inline void StepToRow(S& s, bool forward) {
    int32_t start = s.Value();

    for (int32_t guard = 0; guard <= MAX_VALUES; guard++) {
        if (!s.Step(forward)) {
            break;
        }

        if (s.HasRow(s.Value()) || s.Value() == start) {
            return;
        }
    }

    if (s.Value() != start) {
        s.Set(start);
    }
}

}  // namespace BleakholdCustomize

#endif
