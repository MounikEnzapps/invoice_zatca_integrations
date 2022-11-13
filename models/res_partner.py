# -*- coding: utf-8 -*-
from odoo import fields, models, exceptions, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    building_no = fields.Char('Building Number', help="https://splonline.com.sa/en/national-address-1/")
    additional_no = fields.Char('Additional Number', help="https://splonline.com.sa/en/national-address-1/")
    district = fields.Char('District')
    country_id_name = fields.Char(related="country_id.name")
    # bt_46-1 (BR-KSA-14)
    buyer_identification = fields.Selection([('NAT', 'National ID'), ('IQA', 'Iqama Number'),
                                             ('PAS', 'Passport ID'),
                                             ('CRN', 'Commercial Registration number'),
                                             ('MOM', 'Momra license'), ('MLS', 'MLSD license'),
                                             ('SAG', 'Sagia license'), ('GCC', 'GCC ID'),
                                             ('OTH', 'Other OD'),
                                             ('TIN', 'Tax Identification Number'), ('700', '700 Number')],
                                            string="Buyer Identification", default='TIN', required=1,
                                            help="In case multiple IDs exist then one of the above must be entered")
    # bt_46 (BR-KSA-14)
    buyer_identification_no = fields.Char(string="Buyer Identification Number", required=1)

    def write(self, vals):
        res = super(ResPartner, self).write(vals)
        # BR-KSA-40
        for record in self:
            if record.vat:
                if len(str(record.vat)) != 15:
                    raise exceptions.ValidationError('Vat must be exactly 15 minutes')
                if str(record.vat)[0] != '3' or str(record.vat)[-1] != '3':
                    raise exceptions.ValidationError('Vat must start/end with 3')
            # BR-KSA-65
            if record.additional_no:
                if len(str(record.additional_no)) != 4:
                    raise exceptions.ValidationError('Additional Number must be exactly 4 digits')
            # BR-KSA-67
            if record.country_id_name == 'SA' and len(str(record.zip)) != 5:
                raise exceptions.ValidationError('zip must be exactly 5 digits in case of SA')
        return res
