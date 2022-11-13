# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import date
from datetime import datetime
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError
import calendar


class ZatcaEinvoiceConfiguration(models.Model):
    _name = "zatca.einvoice.configuration"
    _order = "id desc"


    user_name = fields.Char('User Name')
    password = fields.Char('Password')
    request_id = fields.Char('Request Id')
    active = fields.Boolean(default=True)
    reporting_url = fields.Char(string='Reporting URL')
    clearance_url = fields.Char(string='Clearance URL')
    compliance_url = fields.Char(string='Compliance URL')
    compliance_inv_url = fields.Char(string='Compliance Invoice URL')
    production_url = fields.Char(string='Production URL')
    company_id = fields.Many2one('res.company',string='Company Name')
    certificate = fields.Char(string='Certificate')
    private_key = fields.Char(string="Private Key")
    hash = fields.Char(string="Hash")
    xml_file_text = fields.Text(string="XML DATA")



    def create_access(self):
        import requests
        from dateutil.relativedelta import relativedelta

        url = self.url
        # url = "https://gsp.adaequare.com/gsp/authenticate"

        querystring = {"grant_type": "token"}

        headers = {
            # 'gspappid': "497B67EC747146CF977B504EFAC10F23",
            'gspappid': self.asp_id,
            # 'gspappsecret': "3C2D0A45GF3FFG4C3FGB90AGA4D7FD2C8D26",
            'gspappsecret': self.password,
            'cache-control': "no-cache",
            # 'postman-token': "422a5a9a-f0f2-8898-3c78-e666a9701291"
            'postman-token': self.postman_token
        }

        response = requests.request("POST", url, headers=headers, params=querystring)

        print(response.text)
        # if response.text.split('success":', 1)[1].rsplit(',')[0] == 'true':
        self.access_token = response.text.split('access_token":"', 1)[1].partition('"')[0]
        self.access_date = datetime.now()
        self.no_of_calls += 1
        self.access_exp_date = datetime.now() + relativedelta(day=datetime.now().day + 1)
        # else:
        #     print('dfdgd')
        #     message = response.text.split('message":', 1)[1].rsplit(',')[0]
        #     raise UserError(message)

