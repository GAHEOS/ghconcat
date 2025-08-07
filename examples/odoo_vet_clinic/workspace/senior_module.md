===== addons/gaheos_vet_clinic/__init__.py =====
```python
from . import models
```

===== addons/gaheos_vet_clinic/__manifest__.py =====
```python
{
    "name": "Gaheos Veterinary Clinic",
    "version": "17.0.1.0.0",
    "category": "Vertical",
    "summary": "Minimal veterinary management for small clinics.",
    "author": "Your Company",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/vet_security.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}
```

===== addons/gaheos_vet_clinic/models/__init__.py =====
```python
from . import vet_owner
from . import vet_pet
from . import vet_visit
```

===== addons/gaheos_vet_clinic/models/vet_owner.py =====
```python
from odoo import fields, models


class VetOwner(models.Model):
    """
    Veterinary owner model storing contact information about
    the pet owners.
    """

    _name = "gaheos.vet.owner"
    _description = "Veterinary Owner"

    name: fields.Char = fields.Char(required=True)
    phone: fields.Char = fields.Char()
    email: fields.Char = fields.Char()
```

===== addons/gaheos_vet_clinic/models/vet_pet.py =====
```python
from odoo import fields, models


class VetPet(models.Model):
    """
    Model representing a pet belonging to a veterinary owner.
    """

    _name = "gaheos.vet.pet"
    _description = "Veterinary Pet"

    name: fields.Char = fields.Char(required=True)
    owner_id: fields.Many2one = fields.Many2one(
        comodel_name="gaheos.vet.owner",
        string="Owner",
        ondelete="cascade",
        required=True,
    )
    species: fields.Selection = fields.Selection(
        selection=[
            ("dog", "Dog"),
            ("cat", "Cat"),
            ("other", "Other"),
        ],
        string="Species",
    )
    birthdate: fields.Date = fields.Date()
```

===== addons/gaheos_vet_clinic/models/vet_visit.py =====
```python
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class VetVisit(models.Model):
    """
    Veterinary visit/consultation record.
    """

    _name = "gaheos.vet.visit"
    _description = "Veterinary Visit"
    _order = "visit_date desc"

    pet_id: fields.Many2one = fields.Many2one(
        comodel_name="gaheos.vet.pet",
        string="Pet",
        ondelete="cascade",
        required=True,
    )
    visit_date: fields.Datetime = fields.Datetime(
        string="Visit Date", default=lambda self: fields.Datetime.now(), required=True
    )
    weight: fields.Float = fields.Float()
    notes: fields.Text = fields.Text()

    @api.constrains("visit_date")
    def _check_visit_date(self) -> None:
        """
        Ensure the visit date is not in the future.
        """
        now = fields.Datetime.context_timestamp(self, datetime.utcnow())
        for record in self:
            if record.visit_date and record.visit_date > now:
                raise ValidationError("A visit cannot be set in the future.")
```

===== addons/gaheos_vet_clinic/security/vet_security.xml =====
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Veterinary User -->
    <record id="group_vet_user" model="res.groups">
        <field name="name">Veterinary User</field>
        <field name="category_id" ref="base.module_category_services"/>
    </record>

    <!-- Veterinary Manager -->
    <record id="group_vet_manager" model="res.groups">
        <field name="name">Veterinary Manager</field>
        <field name="category_id" ref="base.module_category_services"/>
        <field name="implied_ids" eval="[(4, ref('group_vet_user'))]"/>
    </record>
</odoo>
```

===== addons/gaheos_vet_clinic/security/ir.model.access.csv =====
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_vet_owner_user,vet.owner user,model_gaheos_vet_owner,gaheos_vet_clinic.group_vet_user,1,1,1,1
access_vet_owner_manager,vet.owner manager,model_gaheos_vet_owner,gaheos_vet_clinic.group_vet_manager,1,1,1,1
access_vet_pet_user,vet.pet user,model_gaheos_vet_pet,gaheos_vet_clinic.group_vet_user,1,1,1,1
access_vet_pet_manager,vet.pet manager,model_gaheos_vet_pet,gaheos_vet_clinic.group_vet_manager,1,1,1,1
access_vet_visit_user,vet.visit user,model_gaheos_vet_visit,gaheos_vet_clinic.group_vet_user,1,1,1,0
access_vet_visit_manager,vet.visit manager,model_gaheos_vet_visit,gaheos_vet_clinic.group_vet_manager,1,1,1,1
```