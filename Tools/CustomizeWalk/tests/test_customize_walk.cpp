// Tests of WoW/Common/BleakholdCustomize.h, the model of the customization arrows' walk behind the picker's natives
// (GetCharCustomizationInfo, SetCharCustomizationRaw, RandomizeCharCustomization(keepMask), the barbershop's
// GetBarberShopStyleInfo returns 5-7, SetBarberShopStyleData and its skin step). The model is held against "Stock",
// a transliteration of the CharacterComponent.cpp functions the arrows call (SetNext*/SetPrev*/SetRandom*, the
// setters' own checks, ComponentFlagsMatch, BuildComponentArray), on generated tables with gaps, hidden rows and
// Death Knight rows, in every context and both classes:
//   * one arrow press from any look lands where the model's list says (Neighbour), and the model's jump plan to that
//     value gives the very same look, both as the model predicts it and when the plan's setter calls are run on Stock;
//   * pressing an arrow count times walks the whole list in order, so position and count label what the arrows reach;
//   * the barbershop skin step never stops on a skin without a BarberShopStyle row and lands on the next one that has
//     one; on complete rows it is the stock single step;
//   * Randomize with locked rows keeps them and fits the rolled ones to them; without locks it is the stock sequence.
// run_tests.sh builds and runs it. With --dbc DIR (a folder with CharSections.dbc, CharacterFacialHairStyles.dbc and
// BarberShopStyle.dbc, dev only, never committed) the same checks run on those tables and it prints the creation counts.
#include "WoW/Common/BleakholdCustomize.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace BC = BleakholdCustomize;

namespace {
    int s_failed = 0;
    long s_checks = 0;

    void Check(bool ok, const char* what) {
        s_checks++;

        if (!ok) {
            s_failed++;

            if (s_failed <= 40) {
                printf("FAIL: %s\n", what);
            }
        }
    }

    // ---------------------------------------------------------------------------------------- the tables

    struct Row {
        int32_t section;
        int32_t variation;
        int32_t color;
        uint32_t flags;
    };

    struct ColorList {
        int32_t numColors = 0;
        bool allocated = false;
        std::vector<const Row*> color;
    };

    struct VariationList {
        int32_t numVariations = 0;
        bool allocated = false;
        std::vector<ColorList> variation;
    };

    // One race and sex of BuildComponentArray's lookup (rows sorted by section, variation, colour; the last row of a
    // key wins), plus its CharacterFacialHairStyles count.
    struct RaceSex {
        std::vector<Row> rows;
        VariationList section[5];
        int32_t facialStyles = 0;

        void Build() {
            std::stable_sort(rows.begin(), rows.end(), [](const Row& a, const Row& b) {
                if (a.section != b.section) {
                    return a.section < b.section;
                }

                if (a.variation != b.variation) {
                    return a.variation < b.variation;
                }

                return a.color < b.color;
            });

            for (auto& s : section) {
                s = VariationList();
            }

            for (const Row& r : rows) {
                VariationList& list = section[r.section];
                list.numVariations = std::max(list.numVariations, r.variation + 1);
            }

            for (auto& list : section) {
                if (list.numVariations > 0) {
                    list.allocated = true;
                    list.variation.resize(list.numVariations);
                }
            }

            for (const Row& r : rows) {
                ColorList& colors = section[r.section].variation[r.variation];
                colors.numColors = std::max(colors.numColors, r.color + 1);
            }

            for (auto& list : section) {
                for (auto& colors : list.variation) {
                    if (colors.numColors > 0) {
                        colors.allocated = true;
                        colors.color.assign(colors.numColors, nullptr);
                    }
                }
            }

            for (const Row& r : rows) {
                section[r.section].variation[r.variation].color[r.color] = &r;
            }
        }
    };

    // ------------------------------------------------------------- Stock: CharacterComponent.cpp transliterated

    // ComponentFlagsMatch (ComponentUtils.cpp)
    bool StockFlagsMatch(uint32_t flags, int32_t selection) {
        switch (selection) {
            case 0: return (flags & 0x1) && !(flags & 0xC);
            case 1: return (flags & 0x1) && (flags & 0x14) && !(flags & 0x8);
            case 2: return (flags & 0x3) && !(flags & 0xC);
            case 3: return (flags & 0x3) && (flags & 0x14) && !(flags & 0x8);
            case 4: return true;
            case 5: return !(flags & 0xC);
            case 6: return (flags & 0x14) && !(flags & 0x8);
            default: return false;
        }
    }

    // GetSelectionFromContext
    int32_t StockSelection(int32_t context, int32_t classID) {
        switch (context) {
            case 1: return (classID == 6) + 2;
            case 2: return 4;
            case 3: return (classID == 6) + 5;
            default: return classID == 6;
        }
    }

    enum { V_SKIN = 0, V_FACE = 1, V_FACIAL = 2, V_HAIR = 3, V_UNDER = 4 };

    // The component state the arrows change, and the functions they call. Loops carry a guard: where the stock
    // loop never ends (no value fits at all and the start is off the walk), "hung" is set and the result is not used.
    // The stock SetPrevFacialFeature read keepRec without a null check (CRITIC 6; CharacterComponent.cpp now checks it,
    // BLEAKHOLD(glow)): "crashed" records where the old code read through null, and the step goes on as the checked
    // code and SetNextFacialFeature do.
    struct Stock {
        const RaceSex* t;
        int32_t context;
        int32_t classID;
        bool npc;
        uint32_t skin, face, hairStyle, hairColor, facial;
        bool hung = false;
        bool crashed = false;
        uint32_t rng = 1;

        int32_t Sel() const {
            return StockSelection(this->context, this->classID);
        }

        int32_t NumVariations(int32_t v) const {
            const VariationList& list = this->t->section[v];
            return list.allocated ? list.numVariations : 0;
        }

        int32_t NumColors(int32_t v, int32_t variationIndex) const {
            const VariationList& list = this->t->section[v];

            if (!list.allocated || variationIndex >= list.numVariations || list.numVariations <= 0 || variationIndex < 0 || !list.variation[variationIndex].allocated) {
                return 0;
            }

            return list.variation[variationIndex].numColors;
        }

        const Row* Rec(int32_t v, int32_t variationIndex, int32_t colorIndex, bool* found) const {
            if (v >= 0 && v < 5 && variationIndex >= 0) {
                const VariationList& list = this->t->section[v];

                if (variationIndex < list.numVariations && list.numVariations && colorIndex >= 0) {
                    int32_t numColors = list.variation[variationIndex].numColors;

                    if (colorIndex < numColors && numColors) {
                        if (found) {
                            *found = true;
                        }

                        return list.variation[variationIndex].color[colorIndex];
                    }
                }
            }

            if (found) {
                *found = false;
            }

            return nullptr;
        }

        bool ValidateBase(int32_t v, int32_t variationIndex, int32_t colorIndex) const {
            bool found = false;
            this->Rec(v, variationIndex, colorIndex, &found);
            return found;
        }

        bool M(const Row* r) const {
            return r && StockFlagsMatch(r->flags, this->Sel());
        }

        // the setters' effect on the look
        void SetSkinColor(int32_t skinID) {
            this->skin = skinID;
        }

        void SetFace(int32_t faceID) {
            if (this->npc) {
                return;
            }

            const Row* skinRec = this->Rec(V_SKIN, 0, this->skin, nullptr);

            if (skinRec && (skinRec->flags & 0x8)) {
                return;
            }

            if (!this->ValidateBase(V_FACE, faceID, this->skin)) {
                return;
            }

            this->face = faceID;
        }

        void SetHairColor(int32_t hairColorID) {
            if (!this->ValidateBase(V_HAIR, this->hairStyle, hairColorID)) {
                return;
            }

            this->hairColor = hairColorID;
        }

        void SetHairStyle(int32_t hairStyleID) {
            if (!this->ValidateBase(V_HAIR, hairStyleID, this->hairColor)) {
                return;
            }

            this->hairStyle = hairStyleID;
        }

        void SetBeardStyle(int32_t facialHairID) {
            if (facialHairID < 0 || facialHairID > this->t->facialStyles) {
                return;
            }

            this->facial = facialHairID;
        }

        bool SetNextSkin() {
            int32_t numColors = this->NumColors(V_SKIN, 0);

            if (numColors <= 0) {
                return false;
            }

            int32_t skinID = this->skin + 1;

            if (skinID >= numColors) {
                skinID = 0;
            }

            if (skinID == static_cast<int32_t>(this->skin)) {
                return false;
            }

            const Row* skinRec;

            for (int32_t guard = 0;; guard++) {
                if (guard > 1000) {
                    this->hung = true;
                    return false;
                }

                skinRec = this->Rec(V_SKIN, 0, skinID, nullptr);
                const Row* faceRec = this->Rec(V_FACE, this->face, skinID, nullptr);
                const Row* underwearRec = this->Rec(V_UNDER, 0, skinID, nullptr);

                if (this->M(skinRec) && this->M(faceRec) && (this->context == 2 || this->M(underwearRec))) {
                    break;
                }

                if (++skinID >= numColors) {
                    skinID = 0;
                }

                if (skinID == static_cast<int32_t>(this->skin)) {
                    return false;
                }
            }

            this->SetSkinColor(skinRec->color);
            return true;
        }

        bool SetPrevSkin() {
            int32_t numColors = this->NumColors(V_SKIN, 0);

            if (numColors <= 0) {
                return false;
            }

            int32_t skinID = this->skin - 1;

            if (skinID < 0) {
                skinID = numColors - 1;
            }

            if (skinID == static_cast<int32_t>(this->skin)) {
                return false;
            }

            const Row* skinRec;

            for (int32_t guard = 0;; guard++) {
                if (guard > 1000) {
                    this->hung = true;
                    return false;
                }

                skinRec = this->Rec(V_SKIN, 0, skinID, nullptr);
                const Row* faceRec = this->Rec(V_FACE, this->face, skinID, nullptr);
                const Row* underwearRec = this->Rec(V_UNDER, 0, skinID, nullptr);

                if (this->M(skinRec) && this->M(faceRec) && (this->context == 2 || this->M(underwearRec))) {
                    break;
                }

                if (--skinID < 0) {
                    skinID = numColors - 1;
                }

                if (skinID == static_cast<int32_t>(this->skin)) {
                    return false;
                }
            }

            this->SetSkinColor(skinRec->color);
            return true;
        }

        bool StepFace(int32_t colorOffset, bool forward) {
            int32_t numVariations = this->NumVariations(V_FACE);

            if (numVariations <= 0) {
                return false;
            }

            int32_t faceID = forward ? this->face + 1 : static_cast<int32_t>(this->face) - 1;

            if (forward && faceID >= numVariations) {
                faceID = 0;
            }

            if (!forward && faceID < 0) {
                faceID = numVariations - 1;
            }

            if (faceID == static_cast<int32_t>(this->face)) {
                return false;
            }

            int32_t skinID = 0;

            for (int32_t guard = 0;; guard++) {
                if (guard > 1000) {
                    this->hung = true;
                    return false;
                }

                int32_t numColors = this->NumColors(V_FACE, faceID);
                bool matched = false;

                for (int32_t i = 0, inner = 0; i < numColors; i = skinID + 1, inner++) {
                    if (inner > 1000) {
                        this->hung = true;
                        return false;
                    }

                    skinID = (i + colorOffset) % numColors;
                    const Row* faceRec = this->Rec(V_FACE, faceID, skinID, nullptr);
                    const Row* skinRec = this->Rec(V_SKIN, 0, skinID, nullptr);
                    const Row* underwearRec = this->Rec(V_UNDER, 0, skinID, nullptr);

                    if (this->M(faceRec) && this->M(skinRec) && (this->context == 2 || this->M(underwearRec))) {
                        matched = true;
                        break;
                    }
                }

                if (matched) {
                    break;
                }

                if (forward) {
                    if (++faceID >= numVariations) {
                        faceID = 0;
                    }
                } else if (--faceID < 0) {
                    faceID = numVariations - 1;
                }

                if (faceID == static_cast<int32_t>(this->face)) {
                    return false;
                }
            }

            const Row* faceRec = this->Rec(V_FACE, faceID, this->skin, nullptr);
            const Row* skinRec = this->Rec(V_SKIN, 0, this->skin, nullptr);
            const Row* underwearRec = this->Rec(V_UNDER, 0, this->skin, nullptr);

            if (!this->M(faceRec) || !this->M(skinRec) || (this->context != 2 && !this->M(underwearRec))) {
                this->SetSkinColor(skinID);
            }

            this->SetFace(faceID);
            return true;
        }

        int32_t NumFeaturesAtColor(int32_t hairColorID) const {
            int32_t numVariations = this->NumVariations(V_FACIAL);

            if (!numVariations) {
                return this->t->facialStyles;
            }

            int32_t count = 0;

            for (int32_t i = 0; i < numVariations; i++) {
                if (this->M(this->Rec(V_FACIAL, i, hairColorID, nullptr))) {
                    count++;
                }
            }

            return count;
        }

        int32_t NthFeature(int32_t index) const {
            bool found;
            this->Rec(V_FACIAL, this->facial, this->hairColor, &found);

            if (!found) {
                return index < this->t->facialStyles ? index : -1;
            }

            int32_t count = this->NumFeaturesAtColor(this->hairColor);

            if (count <= 0) {
                return -1;
            }

            int32_t matched = 0;

            for (int32_t i = 0; i < count; i++) {
                if (this->M(this->Rec(V_FACIAL, i, this->hairColor, nullptr))) {
                    if (index == matched) {
                        return i;
                    }

                    matched++;
                }
            }

            return -1;
        }

        bool StepHairStyle(bool forward) {
            int32_t numVariations = this->NumVariations(V_HAIR);

            if (numVariations <= 0) {
                return false;
            }

            int32_t hairStyleID = forward ? this->hairStyle + 1 : static_cast<int32_t>(this->hairStyle) - 1;

            if (forward && hairStyleID >= numVariations) {
                hairStyleID = 0;
            }

            if (!forward && hairStyleID < 0) {
                hairStyleID = numVariations - 1;
            }

            if (hairStyleID == static_cast<int32_t>(this->hairStyle)) {
                return false;
            }

            const Row* rec = nullptr;

            for (int32_t guard = 0;; guard++) {
                if (guard > 1000) {
                    this->hung = true;
                    return false;
                }

                int32_t numColors = this->NumColors(V_HAIR, hairStyleID);
                int32_t color;

                for (color = 0; color < numColors; color++) {
                    rec = this->Rec(V_HAIR, hairStyleID, color, nullptr);

                    if (this->M(rec)) {
                        break;
                    }
                }

                if (color < numColors) {
                    break;
                }

                if (forward) {
                    if (++hairStyleID >= numVariations) {
                        hairStyleID = 0;
                    }
                } else if (--hairStyleID < 0) {
                    hairStyleID = numVariations - 1;
                }

                if (hairStyleID == static_cast<int32_t>(this->hairStyle)) {
                    return false;
                }
            }

            const Row* keepRec = this->Rec(V_HAIR, hairStyleID, this->hairColor, nullptr);

            if (this->M(keepRec)) {
                this->SetHairStyle(keepRec->variation);
                return true;
            }

            this->SetHairColor(rec->color);
            this->SetHairStyle(rec->variation);
            int32_t facialHairID = this->NthFeature(0);

            if (facialHairID >= 0) {
                this->SetBeardStyle(facialHairID);
            }

            return true;
        }

        bool StepHairColor(bool forward) {
            int32_t numColors = this->NumColors(V_HAIR, this->hairStyle);

            if (numColors <= 0) {
                return false;
            }

            int32_t hairColorID = forward ? this->hairColor + 1 : static_cast<int32_t>(this->hairColor) - 1;

            if (forward && hairColorID >= numColors) {
                hairColorID = 0;
            }

            if (!forward && hairColorID < 0) {
                hairColorID = numColors - 1;
            }

            if (hairColorID == static_cast<int32_t>(this->hairColor)) {
                return false;
            }

            const Row* rec;

            for (int32_t guard = 0;; guard++) {
                if (guard > 1000) {
                    this->hung = true;
                    return false;
                }

                rec = this->Rec(V_HAIR, this->hairStyle, hairColorID, nullptr);

                if (this->M(rec)) {
                    break;
                }

                if (forward) {
                    if (++hairColorID >= numColors) {
                        hairColorID = 0;
                    }
                } else if (--hairColorID < 0) {
                    hairColorID = numColors - 1;
                }

                if (hairColorID == static_cast<int32_t>(this->hairColor)) {
                    return false;
                }
            }

            this->SetHairColor(rec->color);
            return true;
        }

        bool StepFacial(bool forward) {
            bool found;
            this->Rec(V_FACIAL, this->facial, this->hairColor, &found);

            if (!found) {
                int32_t count = this->t->facialStyles;

                if (forward) {
                    int32_t facialHairID = this->facial + 1;
                    this->SetBeardStyle(facialHairID >= count ? 0 : facialHairID);
                } else {
                    int32_t facialHairID = static_cast<int32_t>(this->facial) - 1;
                    this->SetBeardStyle(facialHairID >= 0 ? facialHairID : count - 1);
                }

                return true;
            }

            int32_t numVariations = this->NumVariations(V_FACIAL);

            if (numVariations <= 0) {
                return false;
            }

            int32_t facialHairID = forward ? this->facial + 1 : static_cast<int32_t>(this->facial) - 1;

            if (forward && facialHairID >= numVariations) {
                facialHairID = 0;
            }

            if (!forward && facialHairID < 0) {
                facialHairID = numVariations - 1;
            }

            if (facialHairID == static_cast<int32_t>(this->facial)) {
                return false;
            }

            const Row* rec = nullptr;

            for (int32_t guard = 0;; guard++) {
                if (guard > 1000) {
                    this->hung = true;
                    return false;
                }

                int32_t numColors = this->NumColors(V_FACIAL, facialHairID);
                int32_t color;

                for (color = 0; color < numColors; color++) {
                    rec = this->Rec(V_FACIAL, facialHairID, color, nullptr);

                    if (this->M(rec)) {
                        break;
                    }
                }

                if (color < numColors) {
                    break;
                }

                if (forward) {
                    if (++facialHairID >= numVariations) {
                        facialHairID = 0;
                    }
                } else if (--facialHairID < 0) {
                    facialHairID = numVariations - 1;
                }

                if (facialHairID == static_cast<int32_t>(this->facial)) {
                    return false;
                }
            }

            const Row* keepRec = this->Rec(V_FACIAL, facialHairID, this->hairColor, nullptr);

            if (!forward && !keepRec) {
                this->crashed = true;
            }

            if (this->M(keepRec)) {
                this->SetBeardStyle(keepRec->variation);
            } else {
                this->SetHairColor(rec->color);
                this->SetBeardStyle(rec->variation);
            }

            return true;
        }

        bool Step(int32_t row, bool forward, int32_t colorOffset) {
            switch (row) {
                case BC::ROW_SKIN: return forward ? this->SetNextSkin() : this->SetPrevSkin();
                case BC::ROW_FACE: return this->StepFace(colorOffset, forward);
                case BC::ROW_HAIR_STYLE: return this->StepHairStyle(forward);
                case BC::ROW_HAIR_COLOR: return this->StepHairColor(forward);
                default: return this->StepFacial(forward);
            }
        }

        // ---- random pickers (SetRandom*, with CRandom::dice_ replaced by a fixed generator)
        int32_t Dice(int32_t n) {
            this->rng = this->rng * 1103515245u + 12345u;
            return n > 0 ? static_cast<int32_t>((static_cast<uint64_t>(n) * this->rng) >> 32) : 0;
        }

        void RandomSkin() {
            int32_t numColors = this->NumColors(V_SKIN, 0);
            std::vector<int32_t> fit;

            for (int32_t i = 0; i < numColors; i++) {
                if (this->M(this->Rec(V_SKIN, 0, i, nullptr))) {
                    fit.push_back(i);
                }
            }

            int32_t index = fit.size() ? this->Dice(static_cast<int32_t>(fit.size())) : 0;

            if (index < static_cast<int32_t>(fit.size())) {
                this->SetSkinColor(fit[index]);
            }
        }

        void RandomFace() {
            int32_t numVariations = this->NumVariations(V_FACE);
            std::vector<int32_t> fit;

            for (int32_t i = 0; i < numVariations; i++) {
                if (this->M(this->Rec(V_FACE, i, this->skin, nullptr))) {
                    fit.push_back(i);
                }
            }

            int32_t index = fit.size() ? this->Dice(static_cast<int32_t>(fit.size())) : 0;

            if (index < static_cast<int32_t>(fit.size())) {
                this->SetFace(fit[index]);
            }
        }

        void RandomHairColor() {
            int32_t numColors = this->NumColors(V_HAIR, this->hairStyle);
            std::vector<int32_t> fit;

            for (int32_t i = 0; i < numColors; i++) {
                if (this->M(this->Rec(V_HAIR, this->hairStyle, i, nullptr))) {
                    fit.push_back(i);
                }
            }

            int32_t index = fit.size() ? this->Dice(static_cast<int32_t>(fit.size())) : 0;

            if (index < static_cast<int32_t>(fit.size())) {
                this->SetHairColor(fit[index]);
            }
        }

        void RandomHairStyle() {
            int32_t numVariations = this->NumVariations(V_HAIR);
            std::vector<int32_t> fit;

            for (int32_t i = 0; i < numVariations; i++) {
                if (this->M(this->Rec(V_HAIR, i, this->hairColor, nullptr))) {
                    fit.push_back(i);
                }
            }

            int32_t index = fit.size() ? this->Dice(static_cast<int32_t>(fit.size())) : 0;

            if (index < static_cast<int32_t>(fit.size())) {
                this->SetHairStyle(fit[index]);
            }
        }

        void RandomFeatures() {
            int32_t numFeatures = this->NumFeaturesAtColor(this->hairColor);
            int32_t index = numFeatures > 0 ? this->Dice(numFeatures) : 0;
            int32_t facialHairID = this->NthFeature(index);

            if (facialHairID >= 0) {
                this->SetBeardStyle(facialHairID);
            }
        }

        BC::Prefs Look() const {
            BC::Prefs p = { static_cast<int32_t>(this->skin), static_cast<int32_t>(this->face), static_cast<int32_t>(this->hairStyle), static_cast<int32_t>(this->hairColor), static_cast<int32_t>(this->facial) };
            return p;
        }

        void SetSkin(int32_t v) {
            this->SetSkinColor(v);
        }

        void Run(const BC::Plan& plan) {
            for (int32_t i = 0; i < plan.count; i++) {
                const BC::Op& op = plan.ops[i];

                switch (op.kind) {
                    case BC::OP_SKIN: this->SetSkinColor(op.value); break;
                    case BC::OP_FACE: this->SetFace(op.value); break;
                    case BC::OP_HAIR_COLOR: this->SetHairColor(op.value); break;
                    case BC::OP_HAIR_STYLE: this->SetHairStyle(op.value); break;
                    case BC::OP_BEARD: this->SetBeardStyle(op.value); break;
                    default: break;
                }
            }
        }
    };

    // The model's table over the same lookup.
    struct Table {
        const RaceSex* t;
        int32_t context;
        int32_t classID;
        bool npc;

        int32_t NumVariations(int32_t section) const {
            Stock s = { this->t, this->context, this->classID, this->npc, 0, 0, 0, 0, 0 };
            return s.NumVariations(section);
        }

        int32_t NumColors(int32_t section, int32_t variation) const {
            Stock s = { this->t, this->context, this->classID, this->npc, 0, 0, 0, 0, 0 };
            return s.NumColors(section, variation);
        }

        BC::Cell Get(int32_t section, int32_t variation, int32_t color) const {
            Stock s = { this->t, this->context, this->classID, this->npc, 0, 0, 0, 0, 0 };
            bool found = false;
            const Row* r = s.Rec(section, variation, color, &found);
            BC::Cell c = { found, r != nullptr, r ? r->flags : 0 };
            return c;
        }

        bool Match(uint32_t flags) const {
            return StockFlagsMatch(flags, StockSelection(this->context, this->classID));
        }

        int32_t FacialStyles() const {
            return this->t->facialStyles;
        }

        bool AnyUnderwear() const {
            return this->context == 2;
        }

        bool NpcSkin() const {
            return this->npc;
        }
    };

    bool Same(const BC::Prefs& a, const BC::Prefs& b) {
        return a.skin == b.skin && a.face == b.face && a.hairStyle == b.hairStyle && a.hairColor == b.hairColor && a.facial == b.facial;
    }

    std::string Describe(const BC::Prefs& p) {
        char buf[96];
        snprintf(buf, sizeof(buf), "skin %d face %d style %d colour %d features %d", p.skin, p.face, p.hairStyle, p.hairColor, p.facial);
        return buf;
    }

    // ------------------------------------------------------------------------------------- generated tables

    uint32_t s_seed = 12345;

    uint32_t Next() {
        s_seed ^= s_seed << 13;
        s_seed ^= s_seed >> 17;
        s_seed ^= s_seed << 5;
        return s_seed;
    }

    int32_t Rand(int32_t n) {
        return n > 0 ? static_cast<int32_t>(Next() % static_cast<uint32_t>(n)) : 0;
    }

    uint32_t RandFlags() {
        static const uint32_t s_flags[] = { 0x1, 0x1, 0x1, 0x1, 0x11, 0x11, 0x3, 0x2, 0x5, 0x5, 0x9, 0x15, 0x14, 0x0, 0x8, 0x19 };
        return s_flags[Rand(sizeof(s_flags) / sizeof(s_flags[0]))];
    }

    void AddGrid(RaceSex& rs, int32_t section, int32_t variations, int32_t colors, int32_t presence, bool jitterColors) {
        for (int32_t v = 0; v < variations; v++) {
            if (Rand(10) == 0) {
                continue;  // a variation with no rows at all
            }

            int32_t n = jitterColors ? std::max(1, colors + Rand(3) - 1) : colors;

            for (int32_t c = 0; c < n; c++) {
                if (Rand(100) < presence) {
                    rs.rows.push_back(Row{ section, v, c, RandFlags() });

                    if (Rand(40) == 0) {
                        rs.rows.push_back(Row{ section, v, c, RandFlags() });  // a repeated key: the last one wins
                    }
                }
            }
        }
    }

    RaceSex Generate() {
        RaceSex rs;
        int32_t skins = 1 + Rand(12);
        int32_t faces = 1 + Rand(8);
        int32_t styles = 1 + Rand(8);
        int32_t colors = 1 + Rand(10);
        AddGrid(rs, V_SKIN, 1, skins, 90, false);
        AddGrid(rs, V_FACE, faces, skins, 85, true);
        AddGrid(rs, V_UNDER, 1, skins, 90, false);
        AddGrid(rs, V_HAIR, styles, colors, 85, true);

        if (Rand(2)) {
            AddGrid(rs, V_FACIAL, 1 + Rand(8), colors, 85, true);
        }

        rs.facialStyles = Rand(11);
        rs.Build();
        return rs;
    }

    // -------------------------------------------------------------------------------------------- checks

    struct Counters {
        long steps = 0;
        long moved = 0;
        long hung = 0;
        long crashes = 0;
        long walks = 0;
        long stuck = 0;
        long broken = 0;
    };

    Stock MakeStock(const RaceSex& rs, int32_t context, int32_t classID, bool npc, const BC::Prefs& p) {
        Stock s = { &rs, context, classID, npc, static_cast<uint32_t>(p.skin), static_cast<uint32_t>(p.face), static_cast<uint32_t>(p.hairStyle), static_cast<uint32_t>(p.hairColor), static_cast<uint32_t>(p.facial) };
        return s;
    }

    // One arrow press against the model, from look p on row, both ways.
    void CheckPress(const RaceSex& rs, const Table& table, const BC::Prefs& p, int32_t row, int32_t colorOffset, Counters& n) {
        for (int32_t dir = 0; dir < 2; dir++) {
            bool forward = dir == 0;
            Stock stock = MakeStock(rs, table.context, table.classID, table.npc, p);
            bool stockReturned = stock.Step(row, forward, colorOffset);
            n.steps++;

            if (stock.hung) {
                n.hung++;
                continue;
            }

            if (stock.crashed) {
                n.crashes++;
            }

            BC::Prefs after = stock.Look();
            bool moved = !Same(after, p);
            int32_t values[BC::MAX_VALUES];
            int32_t count = BC::List(table, p, row, colorOffset, values, BC::MAX_VALUES);
            int32_t current = BC::RowValue(p, row);

            // the features count-through branch is plain arithmetic; off its range (a value at or past the count,
            // which no step reaches) the stock code wraps differently and SetBeardStyle takes the count itself
            if (row == BC::ROW_FEATURES && !BC::FeaturesByRows(table, p) && (current >= table.FacialStyles() || current < 0)) {
                continue;
            }

            int32_t target = -1;
            bool expected = BC::Neighbour(values, count, BC::MAX_VALUES, current, forward, &target);
            char what[256];
            snprintf(what, sizeof(what), "row %d %s ctx %d class %d from %s: stock moved %d to %s, model %d to %d", row, forward ? "next" : "prev", table.context, table.classID, Describe(p).c_str(), moved, Describe(after).c_str(), expected, target);

            if (!expected) {
                Check(!moved, what);
                continue;
            }

            Check(stockReturned, what);

            // the press: the model's plan of it gives the stock look, predicted and run on Stock's setters
            BC::Plan plan;
            bool planned = BC::PlanStep(table, p, row, target, colorOffset, &plan);
            Check(planned, what);

            if (!planned) {
                continue;
            }

            Check(Same(plan.result, after), what);
            Stock run = MakeStock(rs, table.context, table.classID, table.npc, p);
            run.Run(plan);
            Check(Same(run.Look(), after), what);
            n.moved += moved;

            // and it lands where the list says, except where the setters' checks stop it (a face on an NPC skin, a
            // hair style whose first colour the old style lacks); PlanJump then refuses, as the jump must not claim
            // a value the arrows do not reach
            BC::Plan jump;
            bool jumps = BC::PlanJump(table, p, row, target, colorOffset, &jump);
            Check(jumps == (BC::RowValue(after, row) == target), what);

            if (!jumps) {
                n.stuck++;
            }
        }
    }

    // Pressing "next" from a listed value moves the label on by one each time, through the whole list and back to
    // the start. A walk is only that while its list stays the same: tables that break the contract's gates (a
    // features value with rows at some hair colours only, a hair style whose colour the old style lacks, an NPC
    // skin under a face in context 2) can change the list or stop a press half way; those walks are counted as
    // broken, not checked, and the DBC run reports how many it met.
    bool SameList(const int32_t* a, int32_t na, const int32_t* b, int32_t nb) {
        return na == nb && std::equal(a, a + std::min(na, BC::MAX_VALUES), b);
    }

    void CheckWalk(const RaceSex& rs, const Table& table, const BC::Prefs& p, int32_t row, int32_t colorOffset, Counters& n) {
        int32_t values[BC::MAX_VALUES];
        int32_t count = BC::List(table, p, row, colorOffset, values, BC::MAX_VALUES);
        BC::Info info = BC::InfoFromList(values, count, BC::MAX_VALUES, BC::RowValue(p, row));

        if (info.position == 0 || count < 2) {
            return;
        }

        Stock stock = MakeStock(rs, table.context, table.classID, table.npc, p);
        int32_t position = info.position;

        for (int32_t k = 0; k < count; k++) {
            BC::Prefs before = stock.Look();
            int32_t expected = -1;
            BC::Neighbour(values, count, BC::MAX_VALUES, BC::RowValue(before, row), true, &expected);
            stock.Step(row, true, colorOffset);

            if (stock.hung) {
                return;
            }

            int32_t now[BC::MAX_VALUES];
            int32_t nowCount = BC::List(table, stock.Look(), row, colorOffset, now, BC::MAX_VALUES);

            if (BC::RowValue(stock.Look(), row) != expected || !SameList(values, count, now, nowCount)) {
                n.broken++;
                return;
            }

            position = position % count + 1;
            BC::Info at = BC::InfoFromList(now, nowCount, BC::MAX_VALUES, BC::RowValue(stock.Look(), row));
            char what[200];
            snprintf(what, sizeof(what), "walk row %d ctx %d from %s: step %d at %d/%d, expected %d/%d", row, table.context, Describe(p).c_str(), k + 1, at.position, at.count, position, count);
            Check(at.position == position && at.count == count, what);
        }

        Check(BC::RowValue(stock.Look(), row) == BC::RowValue(p, row), "walk came back to its start");
        n.walks++;
    }

    // The barbershop's skin step (BleakholdCustomize::StepToRow) on Stock, with rows for some skins.
    struct StockSkinStepper {
        Stock* stock;
        const std::set<int32_t>* rows;

        bool Step(bool forward) {
            return forward ? this->stock->SetNextSkin() : this->stock->SetPrevSkin();
        }

        int32_t Value() const {
            return static_cast<int32_t>(this->stock->skin);
        }

        bool HasRow(int32_t v) const {
            return this->rows->count(v) != 0;
        }

        void Set(int32_t v) {
            this->stock->SetSkinColor(v);
        }
    };

    void CheckBarberSkin(const RaceSex& rs, const Table& table, const BC::Prefs& p, const std::set<int32_t>& rows) {
        if (!rows.count(p.skin)) {
            return;  // CanAlterSkin() is false: the skin selector is not shown
        }

        int32_t values[BC::MAX_VALUES];
        int32_t count = BC::List(table, p, BC::ROW_SKIN, 0, values, BC::MAX_VALUES);
        count = BC::Filter(values, count, BC::MAX_VALUES, [&rows](int32_t v) { return rows.count(v) != 0; });

        for (int32_t dir = 0; dir < 2; dir++) {
            Stock stock = MakeStock(rs, table.context, table.classID, table.npc, p);
            StockSkinStepper stepper = { &stock, &rows };
            BC::StepToRow(stepper, dir == 0);

            if (stock.hung) {
                continue;
            }

            int32_t target = p.skin;
            BC::Neighbour(values, count, BC::MAX_VALUES, p.skin, dir == 0, &target);
            char what[200];
            snprintf(what, sizeof(what), "barber skin %s ctx %d from %s: landed on %u, expected %d", dir == 0 ? "next" : "prev", table.context, Describe(p).c_str(), stock.skin, target);
            Check(rows.count(static_cast<int32_t>(stock.skin)) != 0, what);
            Check(static_cast<int32_t>(stock.skin) == target, what);
        }
    }

    void CheckRandomize(const RaceSex& rs, const Table& table, const BC::Prefs& p) {
        // no lock: RandomizeKeep is the stock sequence, draw for draw
        Stock a = MakeStock(rs, table.context, table.classID, table.npc, p);
        Stock b = a;
        a.RandomSkin();
        a.RandomFace();
        a.RandomHairColor();
        a.RandomHairStyle();
        a.RandomFeatures();
        BC::RandomizeKeep(b, table, 0);
        Check(Same(a.Look(), b.Look()), "RandomizeKeep(0) is the stock Randomize");

        for (uint32_t mask = 1; mask < 32; mask++) {
            Stock r = MakeStock(rs, table.context, table.classID, table.npc, p);
            r.rng = Next();
            BC::RandomizeKeep(r, table, mask);
            BC::Prefs q = r.Look();
            char what[200];
            snprintf(what, sizeof(what), "randomize keep %u ctx %d from %s gave %s", mask, table.context, Describe(p).c_str(), Describe(q).c_str());

            for (int32_t row = 0; row < BC::NUM_ROWS; row++) {
                if (mask & (1u << row)) {
                    Check(BC::RowValue(q, row) == BC::RowValue(p, row), what);
                }
            }

            int32_t values[BC::MAX_VALUES];

            if ((mask & 2) && !(mask & 1) && BC::KeepFaceSkins(table, p, values, BC::MAX_VALUES) > 0) {
                Check(BC::SkinFits(table, q, q.skin), what);
            }

            if ((mask & 16) && !(mask & 8) && BC::KeepFeatureColors(table, p, values, BC::MAX_VALUES) > 0) {
                Check(BC::FeatureValidAt(table, q, q.hairColor), what);
            }
        }
    }

    BC::Prefs RandomLook(const RaceSex& rs) {
        Stock s = { &rs, 0, 1, false, 0, 0, 0, 0, 0 };
        auto pick = [](int32_t domain) { return Rand(4) == 0 ? Rand(domain + 3) : Rand(std::max(domain, 1)); };
        BC::Prefs p;
        p.skin = pick(s.NumColors(V_SKIN, 0));
        p.face = pick(s.NumVariations(V_FACE));
        p.hairStyle = pick(s.NumVariations(V_HAIR));
        p.hairColor = pick(s.NumColors(V_HAIR, p.hairStyle));
        p.facial = pick(std::max(s.NumVariations(V_FACIAL), rs.facialStyles));
        return p;
    }

    void CheckRaceSex(const RaceSex& rs, int32_t looks, Counters& n, const std::set<int32_t>* barberRows) {
        for (int32_t k = 0; k < looks; k++) {
            BC::Prefs p = RandomLook(rs);
            int32_t colorOffset = Rand(4) == 0 ? Rand(30) : p.skin;

            for (int32_t context = 0; context < 4; context++) {
                for (int32_t cls = 0; cls < 2; cls++) {
                    Table table = { &rs, context, cls ? 6 : 1, k % 17 == 3 };

                    for (int32_t row = 0; row < BC::NUM_ROWS; row++) {
                        CheckPress(rs, table, p, row, colorOffset, n);
                        CheckWalk(rs, table, p, row, colorOffset, n);
                    }

                    CheckRandomize(rs, table, p);

                    if (context == 1) {
                        std::set<int32_t> rows;

                        if (barberRows) {
                            rows = *barberRows;
                        } else {
                            Stock s = { &rs, 0, 1, false, 0, 0, 0, 0, 0 };

                            for (int32_t v = 0; v < s.NumColors(V_SKIN, 0); v++) {
                                if (Rand(3)) {
                                    rows.insert(v);
                                }
                            }
                        }

                        CheckBarberSkin(rs, table, p, rows);
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------------------------------ fixed cases

    void FixedCases() {
        // one race and sex: 4 skins (skin 2 Death Knight only, skin 3 hidden), 3 faces (face 1 only on skins 0 and 2),
        // 2 hair styles x 3 colours (style 1 has no colour 0), features rows for 3 values with a gap
        RaceSex rs;
        for (int32_t s = 0; s < 4; s++) {
            uint32_t faceFlags = s == 2 ? 0x5u : 0x1u;
            rs.rows.push_back(Row{ V_SKIN, 0, s, s == 2 ? 0x5u : s == 3 ? 0x9u : 0x1u });
            rs.rows.push_back(Row{ V_UNDER, 0, s, 0x11 });
            rs.rows.push_back(Row{ V_FACE, 0, s, faceFlags });
            rs.rows.push_back(Row{ V_FACE, 2, s, faceFlags });

            if (s == 0 || s == 2) {
                rs.rows.push_back(Row{ V_FACE, 1, s, faceFlags });
            }
        }

        for (int32_t c = 0; c < 3; c++) {
            rs.rows.push_back(Row{ V_HAIR, 0, c, 0x1 });

            if (c) {
                rs.rows.push_back(Row{ V_HAIR, 1, c, 0x1 });
            }

            rs.rows.push_back(Row{ V_FACIAL, 0, c, 0x11 });

            if (c != 1) {
                rs.rows.push_back(Row{ V_FACIAL, 1, c, 0x11 });  // value 1 has no row at colour 1
            }

            rs.rows.push_back(Row{ V_FACIAL, 2, c, 0x11 });
        }

        rs.facialStyles = 3;
        rs.Build();
        Table player = { &rs, 0, 1, false };
        Table dk = { &rs, 0, 6, false };

        BC::Prefs p = { 0, 0, 0, 0, 0 };
        BC::Info skin = BC::RowInfo(player, p, BC::ROW_SKIN, 0);
        Check(skin.position == 1 && skin.count == 2 && skin.raw == 0, "player skins: 0 and 1 (2 is Death Knight only, 3 hidden)");
        BC::Info skinDk = BC::RowInfo(dk, p, BC::ROW_SKIN, 0);
        Check(skinDk.count == 1 && skinDk.position == 0, "Death Knight skins: only 2 (0x5); the current skin 0 is off its walk");

        BC::Info face = BC::RowInfo(player, p, BC::ROW_FACE, 0);
        Check(face.count == 3 && face.position == 1, "faces 0, 1, 2 from skin 0");
        BC::Prefs onSkin1 = { 1, 0, 0, 0, 0 };
        BC::Plan plan;
        Check(BC::PlanJump(player, onSkin1, BC::ROW_FACE, 1, 1, &plan), "face 1 can be reached from skin 1 (it brings skin 0)");
        Check(plan.count == 2 && plan.ops[0].kind == BC::OP_SKIN && plan.ops[0].value == 0 && !plan.ops[0].load && plan.result.face == 1 && plan.result.skin == 0, "face 1 brings skin 0, as SetNextFace does");
        Check(!BC::PlanJump(player, p, BC::ROW_SKIN, 2, 0, &plan), "skin 2 is not on a player's walk");
        Check(!BC::PlanJump(player, p, BC::ROW_SKIN, 3, 0, &plan), "a hidden skin is never on the walk");

        BC::Prefs colour0 = { 0, 0, 0, 0, 0 };
        Check(BC::PlanJump(player, colour0, BC::ROW_HAIR_STYLE, 1, 0, &plan), "hair style 1 from colour 0");
        Check(plan.result.hairStyle == 1 && plan.result.hairColor == 1 && plan.result.facial == 0, "style 1 has no colour 0: it takes colour 1 and the first features value");

        // CRITIC 6: from features 2 at hair colour 1 the stock "previous" lands on value 1, which has no row at colour
        // 1; SetPrevFacialFeature then reads that missing row. The jump takes the colour of value 1's first row.
        BC::Prefs feat = { 0, 0, 0, 1, 2 };
        Stock stock = MakeStock(rs, 0, 1, false, feat);
        stock.StepFacial(false);
        Check(stock.crashed, "the old previous features step read a missing row here (CRITIC 6)");
        Check(BC::PlanJump(player, feat, BC::ROW_FEATURES, 1, 0, &plan), "features 1 from colour 1");
        Check(plan.result.facial == 1 && plan.result.hairColor == 0, "features 1 takes hair colour 0 (its first row)");

        // a race and sex with no features rows counts through CharacterFacialHairStyles
        RaceSex plain = rs;
        plain.rows.erase(std::remove_if(plain.rows.begin(), plain.rows.end(), [](const Row& r) { return r.section == V_FACIAL; }), plain.rows.end());
        plain.facialStyles = 7;
        plain.Build();
        Table plainTable = { &plain, 0, 1, false };
        BC::Prefs f5 = { 0, 0, 0, 0, 5 };
        BC::Info features = BC::RowInfo(plainTable, f5, BC::ROW_FEATURES, 0);
        Check(features.count == 7 && features.position == 6 && features.raw == 5, "features 6/7 by CharacterFacialHairStyles");

        // the barbershop's skin step on Tauren-like rows: rows for skins 0-1 only, skins 2-3 without
        RaceSex tauren;
        for (int32_t s = 0; s < 4; s++) {
            tauren.rows.push_back(Row{ V_SKIN, 0, s, 0x1 });
            tauren.rows.push_back(Row{ V_UNDER, 0, s, 0x1 });
            tauren.rows.push_back(Row{ V_FACE, 0, s, 0x1 });
        }

        tauren.Build();
        std::set<int32_t> barber = { 0, 1 };
        Table world = { &tauren, 1, 1, false };
        BC::Prefs t1 = { 1, 0, 0, 0, 0 };
        Stock ts = MakeStock(tauren, 1, 1, false, t1);
        StockSkinStepper stepper = { &ts, &barber };
        BC::StepToRow(stepper, true);
        Check(ts.skin == 0, "barber skin next from 1 skips 2 and 3 and wraps to 0");
        ts = MakeStock(tauren, 1, 1, false, BC::Prefs{ 0, 0, 0, 0, 0 });
        BC::StepToRow(stepper, false);
        Check(ts.skin == 1, "barber skin previous from 0 skips 3 and 2 and lands on 1");
        std::set<int32_t> all = { 0, 1, 2, 3 };
        StockSkinStepper full = { &ts, &all };
        ts = MakeStock(tauren, 1, 1, false, t1);
        BC::StepToRow(full, true);
        Check(ts.skin == 2, "with a row for every skin the barber step is the stock single step");
        std::set<int32_t> only = { 1 };
        StockSkinStepper alone = { &ts, &only };
        ts = MakeStock(tauren, 1, 1, false, t1);
        BC::StepToRow(alone, true);
        Check(ts.skin == 1, "with no other skin row the barber step goes round and stays");
        (void)world;
    }

    // ------------------------------------------------------------------------------------------ DBC files

    struct Dbc {
        uint32_t records = 0, fields = 0, recordSize = 0, stringSize = 0;
        std::vector<uint8_t> data;

        bool Load(const std::string& path) {
            FILE* f = fopen(path.c_str(), "rb");

            if (!f) {
                return false;
            }

            uint8_t header[20];

            if (fread(header, 1, 20, f) != 20 || memcmp(header, "WDBC", 4)) {
                fclose(f);
                return false;
            }

            memcpy(&this->records, header + 4, 4);
            memcpy(&this->fields, header + 8, 4);
            memcpy(&this->recordSize, header + 12, 4);
            memcpy(&this->stringSize, header + 16, 4);
            this->data.resize(static_cast<size_t>(this->records) * this->recordSize);
            bool ok = fread(this->data.data(), 1, this->data.size(), f) == this->data.size();
            fclose(f);
            return ok;
        }

        uint32_t U(uint32_t record, uint32_t field) const {
            uint32_t v;
            memcpy(&v, &this->data[static_cast<size_t>(record) * this->recordSize + field * 4], 4);
            return v;
        }
    };

    int RunDbc(const std::string& dir) {
        Dbc sections, facial, barber;

        if (!sections.Load(dir + "/CharSections.dbc") || !facial.Load(dir + "/CharacterFacialHairStyles.dbc")) {
            printf("cannot read %s/CharSections.dbc and CharacterFacialHairStyles.dbc\n", dir.c_str());
            return 2;
        }

        bool haveBarber = barber.Load(dir + "/BarberShopStyle.dbc");
        std::map<std::pair<int32_t, int32_t>, RaceSex> races;

        // file order (the client sorts nothing; RaceForge writes it sorted)
        for (uint32_t i = 0; i < sections.records; i++) {
            int32_t race = static_cast<int32_t>(sections.U(i, 1));
            int32_t sex = static_cast<int32_t>(sections.U(i, 2));
            int32_t section = static_cast<int32_t>(sections.U(i, 3));

            if (race <= 0 || race > 40 || sex < 0 || sex > 1 || section < 0 || section > 4) {
                continue;
            }

            races[{ race, sex }].rows.push_back(Row{ section, static_cast<int32_t>(sections.U(i, 8)), static_cast<int32_t>(sections.U(i, 9)), sections.U(i, 7) });
        }

        for (uint32_t i = 0; i < facial.records; i++) {
            int32_t race = static_cast<int32_t>(facial.U(i, 0));
            int32_t sex = static_cast<int32_t>(facial.U(i, 1));

            if (races.count({ race, sex })) {
                races[{ race, sex }].facialStyles++;
            }
        }

        std::map<std::pair<int32_t, int32_t>, std::set<int32_t>> barberSkins;

        if (haveBarber) {
            for (uint32_t i = 0; i < barber.records; i++) {
                if (barber.U(i, 1) == 3) {
                    barberSkins[{ static_cast<int32_t>(barber.U(i, 37)), static_cast<int32_t>(barber.U(i, 38)) }].insert(static_cast<int32_t>(barber.U(i, 39)));
                }
            }
        }

        static const char* s_rowNames[5] = { "skins", "faces", "hair styles", "hair colours", "features" };
        printf("creation counts (player / Death Knight) from the first look the skin walk reaches:\n");
        Counters n;

        for (auto& entry : races) {
            RaceSex& rs = entry.second;
            rs.Build();
            printf("  race %2d sex %d:", entry.first.first, entry.first.second);

            for (int32_t cls = 0; cls < 2; cls++) {
                Table table = { &rs, 0, cls ? 6 : 1, false };
                BC::Prefs p = { 0, 0, 0, 0, 0 };
                int32_t values[BC::MAX_VALUES];

                if (BC::List(table, p, BC::ROW_SKIN, 0, values, BC::MAX_VALUES) > 0) {
                    p.skin = values[0];
                }

                printf(cls ? "  | DK" : " ");

                for (int32_t row = 0; row < BC::NUM_ROWS; row++) {
                    BC::Info info = BC::RowInfo(table, p, row, p.skin);
                    printf(" %s %d", s_rowNames[row], info.count);
                }
            }

            printf("\n");
            auto rows = barberSkins.find(entry.first);
            CheckRaceSex(rs, 60, n, rows != barberSkins.end() ? &rows->second : nullptr);
        }

        if (haveBarber) {
            // every Tauren skin reachable at the barber, both ways, never on a skin without a row
            for (int32_t sex = 0; sex < 2; sex++) {
                auto it = races.find({ 6, sex });

                if (it == races.end()) {
                    continue;
                }

                const RaceSex& rs = it->second;
                const std::set<int32_t>& rows = barberSkins[{ 6, sex }];
                Table world = { &rs, 1, 1, false };
                BC::Prefs p = { rows.empty() ? 0 : *rows.begin(), 0, 0, 0, 0 };
                int32_t values[BC::MAX_VALUES];
                int32_t count = BC::List(world, p, BC::ROW_SKIN, 0, values, BC::MAX_VALUES);
                int32_t reachable = BC::Filter(values, count, BC::MAX_VALUES, [&rows](int32_t v) { return rows.count(v) != 0; });

                for (int32_t dir = 0; dir < 2; dir++) {
                    Stock stock = MakeStock(rs, 1, 1, false, p);
                    StockSkinStepper stepper = { &stock, &rows };
                    std::set<int32_t> seen;

                    for (int32_t k = 0; k < count + 2; k++) {
                        BC::StepToRow(stepper, dir == 0);
                        Check(rows.count(static_cast<int32_t>(stock.skin)) != 0, "Tauren barber step stops only on skins with a row");
                        seen.insert(static_cast<int32_t>(stock.skin));
                    }

                    Check(static_cast<int32_t>(seen.size()) == reachable, "Tauren barber steps reach every skin with a row");
                    printf("Tauren sex %d barber %s: %d skins in the in-world walk, %d with a BarberShopStyle row, %zu reached\n", sex, dir == 0 ? "next" : "prev", count, reachable, seen.size());
                }
            }
        }

        printf("dbc: %ld presses (%ld moved, %ld stopped by the setters' checks, %ld stock hangs skipped, %ld stock previous-features null reads), %ld full walks, %ld broken by the tables\n", n.steps, n.moved, n.stuck, n.hung, n.crashes, n.walks, n.broken);
        return 0;
    }
}

int main(int argc, char** argv) {
    std::string dbc;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--dbc") && i + 1 < argc) {
            dbc = argv[++i];
        }
    }

    FixedCases();
    Counters n;

    for (int32_t i = 0; i < 400; i++) {
        RaceSex rs = Generate();
        CheckRaceSex(rs, 12, n, nullptr);
    }

    printf("generated: %ld presses (%ld moved, %ld stopped by the setters' checks, %ld stock hangs skipped, %ld stock previous-features null reads), %ld full walks, %ld broken by the tables\n", n.steps, n.moved, n.stuck, n.hung, n.crashes, n.walks, n.broken);

    if (!dbc.empty()) {
        int rc = RunDbc(dbc);

        if (rc) {
            return rc;
        }
    }

    printf("%ld checks, %d failed\n", s_checks, s_failed);
    return s_failed ? 1 : 0;
}
