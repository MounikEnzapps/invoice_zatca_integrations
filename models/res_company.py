# -*- coding: utf-8 -*-
from odoo import fields, models, exceptions


class ResCompany(models.Model):
    _inherit = 'res.company'

    # BR-KSA-08
    license = fields.Selection([('CRN', 'Commercial Registration number'),
                                ('MOM', 'Momra license'), ('MLS', 'MLSD license'),
                                ('SAG', 'Sagia license'), ('OTH', 'Other OD')],
                               default='CRN', required=1, string="License",
                               help="In case multiple IDs exist then one of the above must be entered")
    license_no = fields.Char(string="License Number", required=1)

    building_no = fields.Integer('Building Number', help="https://splonline.com.sa/en/national-address-1/")
    additional_no = fields.Char('Additional Number', help="https://splonline.com.sa/en/national-address-1/")
    district = fields.Char('District')
    country_id_name = fields.Char(related="country_id.name")

    def write(self, vals):
        res = super(ResCompany, self).write(vals)
        # BR-KSA-37
        if len(str(self.building_no)) != 4:
            raise exceptions.ValidationError('Building Number must be exactly 4 digits')
        # BR-KSA-64
        if len(str(self.additional_no)) != 4:
            raise exceptions.ValidationError('Additional Number must be exactly 4 digits')
        # BR-KSA-66
        if len(str(self.zip)) != 5:
            raise exceptions.ValidationError('zip must be exactly 5 digits')
        return res
