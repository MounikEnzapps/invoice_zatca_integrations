from odoo import api, fields, models, exceptions
from decimal import Decimal
import uuid


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # BR-KSA-DEC-01 for BT-138 only
    @api.onchange('discount')
    def zatca_onchange_discount(self):
        for res in self:
            res.discount = 100 if res.discount > 100 else (0 if res.discount < 0 else res.discount)

    #BR-KSA-F-04
    @api.onchange('quantity')
    def zatca_BR_KSA_F_04(self):
        self.quantity = 0 if self.quantity < 0 else self.quantity
        self.price_unit = abs(self.price_unit)
