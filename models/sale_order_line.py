# -*- coding: utf-8 -*-
from odoo import fields, models, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # BR-KSA-DEC-01 for BT-138 only
    @api.onchange('discount')
    def zatca_onchange_discount(self):
        for res in self:
            res.discount = 100 if res.discount > 100 else (0 if res.discount < 0 else res.discount)
