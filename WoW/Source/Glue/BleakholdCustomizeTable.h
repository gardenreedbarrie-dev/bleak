#ifndef WOW_SOURCE_GLUE_BLEAKHOLDCUSTOMIZETABLE_H
#define WOW_SOURCE_GLUE_BLEAKHOLDCUSTOMIZETABLE_H

#include <cstdint>
#include "Engine/Source/Tempest/CRandom.h"
#include "WoW/Common/BleakholdCustomize.h"
#include "WoW/Common/ComponentCore/CharacterComponent.h"
#include "WoW/Common/ComponentCore/ComponentUtils.h"
#include "WoW/Common/ComponentCore/Types.h"
#include "WoW/Source/DB/Rec/CharSectionsRec.h"

// BLEAKHOLD(customize): the live option tables (CCharacterComponent::s_chrVarArray built by BuildComponentArray, and
// s_characterFacialHairStylesList) seen as WoW/Common/BleakholdCustomize.h's table, for one component's race, sex and
// class on one screen (COMPONENT_CONTEXT_0 creation and customize, COMPONENT_CONTEXT_1 the barbershop), plus the
// glue between the model's plans and the component's own setters. Used by the glue natives
// (CharacterCreation.cpp) and the barbershop (WoW/Source/Ui/BarberShop.cpp).
class BleakholdComponentTable {
    public:
    BleakholdComponentTable(const CCharacterComponent* component, COMPONENT_CONTEXT context)
        : m_valid(false)
        , m_race(0)
        , m_sex(0)
        , m_selection(COMPONENT_SELECTION_0)
        , m_anyUnderwear(context == COMPONENT_CONTEXT_2)
        , m_npcSkin(false) {
        if (!component || !CCharacterComponent::s_chrVarArray || !CCharacterComponent::s_characterFacialHairStylesList) {
            return;
        }

        const CharacterPreferences& prefs = component->m_data.m_preferences;
        this->m_race = static_cast<int32_t>(prefs.m_raceID);
        this->m_sex = static_cast<int32_t>(prefs.m_sexID);
        this->m_selection = GetSelectionFromContext(context, static_cast<int32_t>(prefs.m_classId));
        this->m_npcSkin = (component->m_data.m_flags & 0x1) != 0;
        this->m_valid = prefs.m_raceID < 0x8000 && prefs.m_sexID < 2 && prefs.m_raceID * 2 + prefs.m_sexID < CCharacterComponent::s_chrVarArrayLength;
    }

    int32_t NumVariations(int32_t section) const {
        if (!this->m_valid || section < 0 || section >= NUM_COMPONENT_VARIATIONS) {
            return 0;
        }

        return ComponentGetNumVariations(CCharacterComponent::s_chrVarArray, this->m_race, this->m_sex, static_cast<COMPONENT_VARIATIONS>(section));
    }

    int32_t NumColors(int32_t section, int32_t variation) const {
        if (!this->m_valid || section < 0 || section >= NUM_COMPONENT_VARIATIONS || variation < 0) {
            return 0;
        }

        return ComponentGetNumColors(CCharacterComponent::s_chrVarArray, this->m_race, this->m_sex, static_cast<COMPONENT_VARIATIONS>(section), variation);
    }

    BleakholdCustomize::Cell Get(int32_t section, int32_t variation, int32_t color) const {
        BleakholdCustomize::Cell cell = { false, false, 0 };

        if (!this->m_valid || section < 0 || section >= NUM_COMPONENT_VARIATIONS) {
            return cell;
        }

        bool found = false;
        CharSectionsRec* rec = ComponentGetSectionsRecord(CCharacterComponent::s_chrVarArray, this->m_race, this->m_sex, static_cast<COMPONENT_VARIATIONS>(section), variation, color, &found);
        cell.inRange = found;
        cell.present = rec != nullptr;
        cell.flags = rec ? static_cast<uint32_t>(rec->m_flags) : 0;
        return cell;
    }

    bool Match(uint32_t flags) const {
        return ComponentFlagsMatch(flags, this->m_selection);
    }

    int32_t FacialStyles() const {
        return this->m_valid ? static_cast<int32_t>(CCharacterComponent::s_characterFacialHairStylesList[this->m_race * 2 + this->m_sex]) : 0;
    }

    bool AnyUnderwear() const {
        return this->m_anyUnderwear;
    }

    bool NpcSkin() const {
        return this->m_npcSkin;
    }

    bool Valid() const {
        return this->m_valid;
    }

    private:
    bool m_valid;
    int32_t m_race;
    int32_t m_sex;
    COMPONENT_SELECTION m_selection;
    bool m_anyUnderwear;
    bool m_npcSkin;
};

inline BleakholdCustomize::Prefs BleakholdLookOf(const CCharacterComponent* component) {
    const CharacterPreferences& prefs = component->m_data.m_preferences;
    BleakholdCustomize::Prefs look = {
        static_cast<int32_t>(prefs.m_skinID),
        static_cast<int32_t>(prefs.m_faceId),
        static_cast<int32_t>(prefs.m_hairStyleId),
        static_cast<int32_t>(prefs.m_hairColorId),
        static_cast<int32_t>(prefs.m_facialHairId),
    };
    return look;
}

// Runs a plan's steps on the component's setters, in the order and with the arguments the stock step uses.
inline void BleakholdRunPlan(CCharacterComponent* component, const BleakholdCustomize::Plan& plan) {
    for (int32_t i = 0; i < plan.count; i++) {
        const BleakholdCustomize::Op& op = plan.ops[i];

        switch (op.kind) {
            case BleakholdCustomize::OP_SKIN:
                component->SetSkinColor(op.value, op.load, true, nullptr);
                break;

            case BleakholdCustomize::OP_FACE:
                component->SetFace(op.value, true, nullptr);
                break;

            case BleakholdCustomize::OP_HAIR_COLOR:
                component->SetHairColor(op.value, op.load, nullptr);
                break;

            case BleakholdCustomize::OP_HAIR_STYLE:
                component->SetHairStyle(op.value, nullptr);
                break;

            case BleakholdCustomize::OP_BEARD:
                component->SetBeardStyle(op.value, true, nullptr);
                break;

            default:
                break;
        }
    }
}

// BleakholdCustomize::RandomizeKeep's view of a component: the stock random pickers and setters.
class BleakholdComponentRandomizer {
    public:
    BleakholdComponentRandomizer(CCharacterComponent* component, COMPONENT_CONTEXT context)
        : m_component(component)
        , m_context(context) {
    }

    BleakholdCustomize::Prefs Look() const {
        return BleakholdLookOf(this->m_component);
    }

    int32_t Dice(int32_t count) {
        return count > 0 ? static_cast<int32_t>(CRandom::dice_(static_cast<uint32_t>(count), g_rndSeed)) : 0;
    }

    void RandomSkin() {
        this->m_component->SetRandomSkin(this->m_context);
    }

    void RandomFace() {
        this->m_component->SetRandomFace(this->m_context);
    }

    void RandomHairColor() {
        this->m_component->SetRandomHairColor(this->m_context);
    }

    void RandomHairStyle() {
        this->m_component->SetRandomHairStyle(this->m_context);
    }

    void RandomFeatures() {
        this->m_component->SetRandomFacialFeature(this->m_context);
    }

    void SetSkin(int32_t skinID) {
        this->m_component->SetSkinColor(skinID, true, true, nullptr);
    }

    void SetHairColor(int32_t hairColorID) {
        this->m_component->SetHairColor(hairColorID, true, nullptr);
    }

    private:
    CCharacterComponent* m_component;
    COMPONENT_CONTEXT m_context;
};

#endif
