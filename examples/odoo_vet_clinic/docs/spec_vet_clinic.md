# Functional Spec – gaheos_vet_clinic

## Purpose

Minimal veterinary management addon for Odoo 17 aimed at small clinics.

## Data model

| Model            | Fields                                                                                                                                  | Notes                     |
|------------------|-----------------------------------------------------------------------------------------------------------------------------------------|---------------------------|
| gaheos.vet.owner | `name: Char` **required**<br>`phone: Char`<br>`email: Char`                                                                             | Basic owner info          |
| gaheos.vet.pet   | `name: Char` **required**<br>`owner_id: Many2one('gaheos.vet.owner')`<br>`species: Selection('dog','cat','other')`<br>`birthdate: Date` | One owner → many pets     |
| gaheos.vet.visit | `pet_id: Many2one('gaheos.vet.pet')`<br>`visit_date: Datetime` (default *now*)<br>`weight: Float`<br>`notes: Text`                      | Basic consultation record |

## Business rules

1. Deleting an owner must cascade to pets and visits (`ondelete='cascade'`).
2. Visits of the future are not allowed.
3. Only users in group **`group_vet_user`** can create/write visits; unlink reserved to **`group_vet_manager`**.

## Minimal UI (out of scope for code generation)

* List views for owners, pets and visits.