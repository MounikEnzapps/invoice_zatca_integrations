# -*- coding: utf-8 -*-
from odoo import fields, models, exceptions
import requests
import base64
import json
import os


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    zatca_link = fields.Char("Api Link", config_parameter='zatca_link',
                             required="1", default="https://gw-apic-gov.gazt.gov.sa/e-invoicing/developer-portal")
    zatca_sdk_path = fields.Char(config_parameter='zatca_sdk_path')
    csr_common_name = fields.Char("Common Name", config_parameter='csr_common_name', required="1")  # CN
    csr_serial_number = fields.Char("EGS Serial Number", config_parameter='csr_serial_number', required="1")  # SN
    csr_organization_identifier = fields.Char("Organization Identifier",
                                              config_parameter='csr_organization_identifier', required="1")  # UID
    csr_organization_unit_name = fields.Char("Organization Unit Name",
                                             config_parameter='csr_organization_unit_name', required="1")  # OU
    csr_organization_name = fields.Char("Organization Name", config_parameter='csr_organization_name', required="1")  # O
    csr_country_name = fields.Char("Country Name", config_parameter='csr_country_name', required="1")  # C
    csr_invoice_type = fields.Char("Invoice Type", config_parameter='csr_invoice_type', required="1")  # title
    csr_location_address = fields.Char("Location", config_parameter='csr_location_address', required="1")  # registeredAddress
    csr_industry_business_category = fields.Char("Industry",
                                                 config_parameter='csr_industry_business_category', required="1")  # BusinessCategory
    csr_otp = fields.Char("Otp", config_parameter='csr_otp', required="1")
    csr_certificate = fields.Char("Certificate", config_parameter='csr_certificate', required="1")
    csr_public_key = fields.Char(string="Publice key")
    def generate_zatca_certificate(self):
        try:
            conf = self.env['ir.config_parameter'].sudo()
            config_cnf = '''
                oid_section = OIDs
                [ OIDs ]
                certificateTemplateName= 1.3.6.1.4.1.311.20.2
                [ req ]
                default_bits = 2048
                emailAddress = myEmail@gmail.com
                req_extensions = v3_req
                x509_extensions = v3_ca
                prompt = no
                default_md = sha256
                req_extensions = req_ext
                distinguished_name = dn
                [ dn ]
                C = ''' + str(conf.get_param("csr_country_name", '')) + '''
                OU = ''' + str(conf.get_param("csr_organization_unit_name", '')) + '''
                O = ''' + str(conf.get_param("csr_organization_name", '')) + '''
                CN = ''' + str(conf.get_param("csr_common_name", '')) + '''
                [ v3_req ]
                basicConstraints = CA:FALSE
                keyUsage = digitalSignature, nonRepudiation, keyEncipherment
                [ req_ext ]
                certificateTemplateName = ASN1:PRINTABLESTRING:ZATCA-Code-Signing
                subjectAltName = dirName:alt_names            
                [ alt_names ]
                SN = ''' + str(conf.get_param("csr_serial_number", '')) + '''
                UID = ''' + str(conf.get_param("csr_organization_identifier", '')) + '''
                title = ''' + str(conf.get_param("csr_invoice_type", '')) + '''
                registeredAddress = ''' + str(conf.get_param("csr_location_address", '')) + '''
                businessCategory = ''' + str(conf.get_param("csr_industry_business_category", '')) + '''
            '''

            f = open('/tmp/zatca.cnf', 'w+')
            f.write(config_cnf)
            f.close()

            private_key = 'openssl ecparam -name secp256k1 -genkey -noout -out /tmp/zatcaprivatekey.pem'
            public_key = 'openssl ec -in /tmp/zatcaprivatekey.pem -pubout -conv_form compressed -out /tmp/zatcapublickey.pem'
            public_key_bin = 'openssl base64 -d -in /tmp/zatcapublickey.pem -out /tmp/zatcapublickey.bin'
            csr = 'openssl req -new -sha256 -key /tmp/zatcaprivatekey.pem -extensions v3_req -config /tmp/zatca.cnf -out /tmp/zatca_taxpayper.csr'
            csr_base64 = "openssl base64 -in /tmp/zatca_taxpayper.csr -out /tmp/zatca_taxpayper_64.csr"

            os.system(private_key)
            os.system(public_key)
            # self.csr_public_key = public_key
            os.system(public_key_bin)
            os.system(csr)
            os.system(csr_base64)
            # filepath = os.popen("find -name 'zatca_sdk'").read()
            # filepath = filepath.replace('zatca_sdk', '').replace('\n', '')
            # self.env['ir.config_parameter'].sudo().set_param("zatca_sdk_path", filepath)

            self.compliance_api()
            # self.compliance_api('/production/csids', 1)
        #     CNF, PEM, CSR created

            # Signature validation
            invoice_name = '.xml'
            signature = 'openssl dgst -verify zatcapublickey.pem -signature zatcapublickey.bin ' + invoice_name
        except Exception as e:
            # raise exceptions.MissingError(e)
            raise exceptions.MissingError('Configuration values missing.')

    def compliance_api(self, endpoint='/compliance', renew=0):
        link = "https://gw-apic-gov.gazt.gov.sa/e-invoicing/developer-portal"
        conf = self.env['ir.config_parameter'].sudo()
        if endpoint == '/compliance':
            zatca_otp = conf.get_param("csr_otp", False)
            headers = {'accept': 'application/json',
                       'OTP': zatca_otp,
                       'Accept-Version': 'V2',
                       'Content-Type': 'application/json'}

            f = open('/tmp/zatca_taxpayper_64.csr', 'r')
            csr = f.read()
            data = {'csr': csr.replace('\n', '')}
        elif endpoint == '/production/csids' and not renew:
            user = conf.get_param("zatca_sb_bsToken", False)
            password = conf.get_param("zatca_sb_secret", False)
            compliance_request_id = conf.get_param("zatca_sb_reqID", False)
            auth = base64.b64encode(('%s:%s' % (user, password)).encode('utf-8')).decode('utf-8')
            headers = {'accept': 'application/json',
                       'Accept-Version': 'V2',
                       'Authorization': 'Basic ' + auth,
                       'Content-Type': 'application/json'}

            data = {'compliance_request_id': compliance_request_id}
        elif endpoint == '/production/csids' and renew:
            user = conf.get_param("zatca_bsToken", False)
            password = conf.get_param("zatca_secret", False)
            auth = base64.b64encode(('%s:%s' % (user, password)).encode('utf-8')).decode('utf-8')
            zatca_otp = conf.get_param("csr_otp", False)
            headers = {'accept': 'application/json',
                       'OTP': zatca_otp,
                       'Accept-Language': 'en',
                       'Accept-Version': 'V2',
                       'Authorization': 'Basic ' + auth,
                       'Content-Type': 'application/json'}
            f = open('/tmp/zatca_taxpayper_64.csr', 'r')
            csr = f.read()
            data = {'csr': csr.replace('\n', '')}
        try:
            req = requests.post(link + endpoint, headers=headers, data=json.dumps(data))
            if req.status_code == 500:
                raise exceptions.AccessError('Invalid Request, zatca, \ncontact system administer')
            elif req.status_code == 400:
                raise exceptions.AccessError('Invalid Request, odoo, \ncontact system administer')
            elif req.status_code == 400:
                raise exceptions.AccessError('Unauthorized, \ncontact system administer')
            elif req.status_code == 200:
                response = json.loads(req.text)
                if endpoint == '/compliance':
                    conf.set_param("zatca_sb_bsToken", response['binarySecurityToken'])
                    conf.set_param("zatca_sb_reqID", response['requestID'])
                    conf.set_param("zatca_sb_secret", response['secret'])
                else:
                    conf.set_param("zatca_bsToken", response['binarySecurityToken'])
                    conf.set_param("zatca_reqID", response['requestID'])
                    conf.set_param("zatca_secret", response['secret'])
                # if endpoint == '/compliance':
                #     self.compliance_api('/production/csids')
                # else:
                #     response['tokenType']
                #     response['dispositionMessage']
        except Exception as e:
            raise exceptions.AccessDenied(e)

    def production_credentials(self):
        self.compliance_api('/production/csids', 0)

    def production_credentials_renew(self):
        self.compliance_api('/production/csids', 1)
