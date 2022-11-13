# -*- coding: utf-8 -*-
from odoo import fields, models, exceptions, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    code_type = fields.Char(string="Barcode Code Type",
                            help="it must be in UPC, GTIN, Customs HS Code and multiple other codes")
