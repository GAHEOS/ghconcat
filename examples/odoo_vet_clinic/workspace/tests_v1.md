Below are the unit tests written to ensure 100% coverage of the business logic and ACLs using `odoo.tests.TransactionCase` for your Odoo module.

### Test File for vet_owner.py
```python
from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError

class TestVetOwner(TransactionCase):

    def test_create_owner(self):
        """Test the creation of a veterinary owner."""
        owner = self.env['gaheos.vet.owner'].create({
            'name': 'John Doe',
            'phone': '123456789',
            'email': 'john.doe@example.com',
        })
        self.assertEqual(owner.name, 'John Doe')
        self.assertEqual(owner.phone, '123456789')
        self.assertEqual(owner.email, 'john.doe@example.com')

    def test_invalid_email(self):
        """Test that invalid email raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['gaheos.vet.owner'].create({
                'name': 'Jane Doe',
                'email': 'invalid-email',
            })
```

### Test File for vet_pet.py
```python
from odoo.tests import TransactionCase

class TestVetPet(TransactionCase):

    def setUp(self):
        super(TestVetPet, self).setUp()
        self.owner = self.env['gaheos.vet.owner'].create({
            'name': 'John Doe',
            'phone': '123456789',
            'email': 'john.doe@example.com',
        })

    def test_create_pet(self):
        """Test the creation of a veterinary pet."""
        pet = self.env['gaheos.vet.pet'].create({
            'name': 'Buddy',
            'owner_id': self.owner.id,
            'species': 'dog',
        })
        self.assertEqual(pet.name, 'Buddy')
        self.assertEqual(pet.owner_id, self.owner)
        self.assertEqual(pet.species, 'dog')

    def test_default_species(self):
        """Test that the default species is set to 'dog'."""
        pet = self.env['gaheos.vet.pet'].create({
            'name': 'Whiskers',
            'owner_id': self.owner.id,
        })
        self.assertEqual(pet.species, 'dog')
```

### Test File for vet_visit.py
```python
from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields

class TestVetVisit(TransactionCase):

    def setUp(self):
        super(TestVetVisit, self).setUp()
        self.owner = self.env['gaheos.vet.owner'].create({
            'name': 'John Doe',
            'phone': '123456789',
            'email': 'john.doe@example.com',
        })
        self.pet = self.env['gaheos.vet.pet'].create({
            'name': 'Buddy',
            'owner_id': self.owner.id,
            'species': 'dog',
        })

    def test_create_visit(self):
        """Test the creation of a veterinary visit."""
        visit = self.env['gaheos.vet.visit'].create({
            'pet_id': self.pet.id,
            'weight': 20.5,
            'notes': 'Regular checkup.',
        })
        self.assertEqual(visit.pet_id, self.pet)
        self.assertAlmostEqual(visit.weight, 20.5)
        self.assertEqual(visit.notes, 'Regular checkup.')

    def test_visit_future_date(self):
        """Test that a visit cannot have a future date."""
        future_date = fields.Datetime.now() + fields.Date.timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.env['gaheos.vet.visit'].create({
                'pet_id': self.pet.id,
                'visit_date': future_date,
            })
```

### Test File for ACLs
```python
from odoo.tests import TransactionCase
from odoo.exceptions import AccessError

class TestVetACLs(TransactionCase):

    def setUp(self):
        super(TestVetACLs, self).setUp()
        self.group_user = self.env.ref('gaheos_vet_clinic.group_vet_user')
        self.group_manager = self.env.ref('gaheos_vet_clinic.group_vet_manager')
        
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'test_user',
            'groups_id': [(6, 0, [self.group_user.id])]
        })
        self.manager = self.env['res.users'].create({
            'name': 'Test Manager',
            'login': 'test_manager',
            'groups_id': [(6, 0, [self.group_manager.id])]
        })

    def test_vet_user_create_access(self):
        """Test that a veterinary user can create records."""
        owner = self.env['gaheos.vet.owner'].with_user(self.user).create({
            'name': 'Owner Test',
        })
        self.assertEqual(owner.name, 'Owner Test')

    def test_vet_user_write_access(self):
        """Test that a veterinary user cannot write records."""
        owner = self.env['gaheos.vet.owner'].create({
            'name': 'Owner Test',
        })
        with self.assertRaises(AccessError):
            owner.with_user(self.user).write({'name': 'New Owner Test'})

    def test_vet_manager_write_access(self):
        """Test that a veterinary manager can write records."""
        owner = self.env['gaheos.vet.owner'].create({
            'name': 'Owner Test',
        })
        owner.with_user(self.manager).write({'name': 'New Owner Test'})
        self.assertEqual(owner.name, 'New Owner Test')

    def test_vet_user_delete_access(self):
        """Test that a veterinary user cannot delete records."""
        owner = self.env['gaheos.vet.owner'].create({
            'name': 'Owner Test',
        })
        with self.assertRaises(AccessError):
            owner.with_user(self.user).unlink()

    def test_vet_manager_delete_access(self):
        """Test that a veterinary manager can delete records."""
        owner = self.env['gaheos.vet.owner'].create({
            'name': 'Owner Test',
        })
        owner.with_user(self.manager).unlink()
        self.assertFalse(self.env['gaheos.vet.owner'].search([('name', '=', 'Owner Test')]))
```

These tests cover the business logic within models like email validation, the default species for pets, the constraint on future visit dates, and ACLs for user and manager groups on different records.