import os
from cryptography.hazmat.backends import default_backend
from odoo import api, fields, models, exceptions
from cryptography import x509
from decimal import Decimal
import lxml.etree as ET
import requests
import hashlib
import base64
import math
import uuid
import json


class AccountMove(models.Model):
    _inherit = "account.move"

    zatca_hash_cleared_invoice = fields.Binary("ZATCA returned cleared invoice", attachment=True, readonly=1)
    zatca_hash_cleared_invoice_name = fields.Char()
    xml_sign_char_data = fields.Text()

    zatca_invoice = fields.Binary("ZATCA generated invoice", attachment=True, readonly=1)
    zatca_invoice_name = fields.Char()
    credit_debit_reason = fields.Char(string="Reasons for issuance of credit / debit note",
                                   help="Reasons as per Article 40 (paragraph 1) of KSA VAT regulations")
    # invoice_date = fields.Datetime(string='Invoice/Bill Date', readonly=True, index=True, copy=False,
    #                                states={'draft': [('readonly', False)]}, default=fields.datetime.now())
    #

    # invoice_date_due = fields.Datetime(string='Due Date', readonly=True, index=True, copy=False,
    #                                states={'draft': [('readonly', False)]})



    zatca_compliance_invoices_api = fields.Html(readonly=1)

    # Never show these fields on front
    invoice_uuid = fields.Char('zatca uuid', readonly=1)
    zatca_invoice_hash = fields.Char(readonly=1)
    zatca_hash_invoice = fields.Binary("ZATCA generated invoice for hash", attachment=True, readonly=1)
    zatca_hash_invoice_name = fields.Char(readonly=1)

    @api.onchange('invoice_date', 'highest_name', 'company_id')
    def _onchange_invoice_date(self):
        if self.datetime_field:
            if not self.invoice_payment_term_id and (not self.invoice_date_due or self.invoice_date_due < self.datetime_field.date()):
                self.invoice_date_due = self.invoice_date

            accounting_date = self.datetime_field
            if not self.is_sale_document(include_receipts=True):
                accounting_date = self._get_accounting_date(self.datetime_field, self._affect_tax_report())
            if accounting_date != self.date:
                self.date = accounting_date
                self._onchange_currency()
            else:
                self._onchange_recompute_dynamic_lines()

    def create_xml_file(self, previous_hash=0):
        amount_verification = 0  # for debug mode
        conf = self.env['ir.config_parameter'].sudo()
        # No longer needed
        # if not previous_hash:
        #     self.create_xml_file(previous_hash=1)

        # STEP # 3 in "5. Signing Process"
        # in https://zatca.gov.sa/ar/E-Invoicing/Introduction/Guidelines/Documents/E-invoicing%20Detailed%20Technical%20Guidelines.pdf
        conf = self.env['ir.config_parameter'].sudo()
        original_certificate = conf.get_param("csr_certificate", '')
        certificate = original_certificate
        sha_256_3 = hashlib.sha256(certificate.encode())
        base_64_3 = base64.b64encode(sha_256_3.hexdigest().encode()).decode('UTF-8')
        if certificate.find('-----BEGIN CERTIFICATE-----') < 0:
            for x in range(1, math.ceil(len(certificate) / 64)):
                certificate = certificate[:64 * x] + '\n' + certificate[64 * x:]
            certificate = "-----BEGIN CERTIFICATE-----\n" + certificate + "\n-----END CERTIFICATE-----"
        cert = x509.load_pem_x509_certificate(certificate.encode(), default_backend())

        signature_certificate = '''<ds:Object>
                                <xades:QualifyingProperties Target="signature" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">
                                    <xades:SignedProperties Id="xadesSignedProperties">
                                        <xades:SignedSignatureProperties>
                                            <xades:SigningTime>''' + fields.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ') + '''</xades:SigningTime>
                                            <xades:SigningCertificate>
                                                <xades:Cert>
                                                    <xades:CertDigest>
                                                        <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                                        <ds:DigestValue>''' + str(base_64_3) + '''</ds:DigestValue>
                                                    </xades:CertDigest>
                                                    <xades:IssuerSerial>
                                                        <ds:X509IssuerName>''' + str(cert.issuer.rfc4514_string()) + '''</ds:X509IssuerName>
                                                        <ds:X509SerialNumber>''' + str(cert.serial_number) + '''</ds:X509SerialNumber>
                                                    </xades:IssuerSerial>
                                                </xades:Cert>
                                            </xades:SigningCertificate>
                                        </xades:SignedSignatureProperties>
                                    </xades:SignedProperties>
                                </xades:QualifyingProperties>
                            </ds:Object>'''
        # STEP # 5 in "5. Signing Process"
        # in https://zatca.gov.sa/ar/E-Invoicing/Introduction/Guidelines/Documents/E-invoicing%20Detailed%20Technical%20Guidelines.pdf

        ubl_2_1 = '''
                <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                 xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
                <sig:UBLDocumentSignatures xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2"
                                           xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2"
                                           xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2">
                    <sac:SignatureInformation>
                        <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
                        <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
                        <ds:Signature Id="signature" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'''
        ubl_2_1 += signature_certificate
        ubl_2_1 += '''  </ds:Signature>
                    </sac:SignatureInformation>
                </sig:UBLDocumentSignatures>
                </Invoice>'''

        # signature_xml = ET.fromstring(signature_certificate)
        signature_xml = ET.fromstring(ubl_2_1)
        signature_xml = signature_xml.getroottree()
        len(base64.b64decode('NGFlMThlNzUxY2FjMzg2NTExZTE0NTkzODg3ZGFmMjA5YzEyMWVhY2ViOTI5ZDA3Mzk1YTM4YjYyZTUwMzE0Mg=='))
        hash = "4ae18e751cac386511e14593887daf209c121eaceb929d07395a38b62e503142"

        signature = '''      <ds:SignedInfo>
                                <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                                <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                                <ds:Reference Id="invoiceSignedData" URI="">
                                    <ds:Transforms>
                                        <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                                            <ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>
                                        </ds:Transform>
                                        <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                                            <ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>
                                        </ds:Transform>
                                        <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
                                            <ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID="QR"])</ds:XPath>
                                        </ds:Transform>
                                        <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                                    </ds:Transforms>
                                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                    <ds:DigestValue>zatca_invoice_hash</ds:DigestValue>
                                </ds:Reference>
                                <ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">
                                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                    <ds:DigestValue>skZ+8g6hyUFzbbTZvJZRyAREMiM=</ds:DigestValue>
                                </ds:Reference>
                            </ds:SignedInfo>
                            <ds:SignatureValue>J3dQSz3nEQd8wagH2CBlip1fj03NTccYAQTGiU/4IhBYzylKxjB09OMBb5vXj2Lv7eXhciRoMmvSF+A9eIUd2a4b5aEm7VBkxIbyGgltNHR8u3oZ7Ee+HNWRAQU+IFCKpZoVA68Bo/g4Gy3pqNQoC7AOghUUXTjvFEBcHVgpt/5wDC8U3PwNfx9hzpU00t/b042GyLECGjPDzr8mGbI09mobT7sSb9oPPzxsC71dph+oU0ug+TAh2NheVih+HWCe870hFJvH3mZ9YcC/lcMXb80Ot+LSjgV8gcTSDz/BaOYLjEGvZrOxmoK2doUZNPi811tbq6nC4jjlrU+NRr5kQA==</ds:SignatureValue>
                            <ds:KeyInfo>
                                <ds:X509Data>
                                    <ds:X509Certificate>''' + str(original_certificate) + '''</ds:X509Certificate>
                                </ds:X509Data>
                            </ds:KeyInfo>'''
        # signature = ''
        # UBL 2.1 sequence
        if self.company_id.currency_id.name != 'SAR':
            # BR-KSA-CL-02
            raise exceptions.ValidationError('currency must be SAR')
        if len(self.invoice_line_ids.ids) <= 0:
            raise exceptions.MissingError('at least one invoice line is required.')
        if self.datetime_field > fields.Datetime.now():
            raise exceptions.ValidationError('Date should be less then or equal to today.')
        if not self.company_id.district or not self.company_id.building_no or not self.company_id.additional_no or\
            not self.company_id.city or not self.company_id.zip or not self.company_id.state_id.id or\
                not self.company_id.country_id.id or not self.company_id.street:
            raise exceptions.ValidationError('Some Values are missing in Company Address')

        bt_3 = '383' if self.debit_origin_id.id else ('381' if self.move_type == 'out_refund' else '388')
        is_tax_invoice = 0 if 'O' in self.invoice_line_ids.tax_ids.mapped('classified_tax_category') else 1

        if is_tax_invoice and not self.partner_id.district or not self.partner_id.building_no or\
                not self.partner_id.additional_no or not self.partner_id.city or not self.partner_id.zip or\
                not self.partner_id.state_id.id or not self.partner_id.country_id.id or not\
                self.partner_id.street:
            message = 'Some Values are missing in Customer Address, which are required for tax invoices'
            raise exceptions.ValidationError(message)

        self.invoice_uuid = self.invoice_uuid if self.invoice_uuid and self.invoice_uuid != '' else str(str(uuid.uuid4()))

        ksa_16 = int(self.env['ir.config_parameter'].sudo().get_param('zatca.icv_counter'))
        ksa_16 += 1
        self.env['ir.config_parameter'].sudo().set_param('zatca.icv_counter', str(ksa_16))

        company_vat = 0
        # BR-KSA-26
        ksa_13 = 0
        previous_invoice = self.env['account.move']
        if self.env['account.move'].search([('id', '<', self.id), ('state', '=', 'posted')]).mapped('id'):
            id = max(self.env['account.move'].search([('id', '<', self.id), ('state', '=', 'posted')]).mapped('id'))
            previous_invoice = self.env['account.move'].browse(id)
            if previous_invoice:
                if not previous_invoice.zatca_invoice_hash:

                    # previous_invoice.hashed_invoice = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
                    previous_invoice.zatca_invoice_hash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
                    ksa_13 = previous_invoice.zatca_invoice_hash
                    print(previous_invoice,'previous_invoice')
                else:
                    ksa_13 = previous_invoice.zatca_invoice_hash
                    print('1234')
            else:
                ksa_13 = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
                print('123')
        else:
            self.zatca_invoice_hash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
            ksa_13 =self.zatca_invoice_hash
        # binary_nodes.text = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
        # binary_nodes.text = pih

        # if not self.zatca_invoice_hash:
        #     self.zatca_invoice_hash =
        # ksa_13 = base64.b64encode(bytes(hashlib.sha256(str(ksa_13).encode('utf-8')).hexdigest(), encoding='utf-8')).decode('UTF-8')
        # self.zatca_invoice_hash = ksa_13
        # signature = 0 if is_tax_invoice else 1
        is_third_party_invoice = 0
        is_nominal_invoice = 0
        is_exports_invoice = 0
        is_summary_invoice = 0
        is_self_billed_invoice = 0  # not allowed in odoo
        # BR-KSA-31 (KSA-2)
        ksa_2 = '01' if is_tax_invoice else '02'  # Simplified in case of tax category O
        ksa_2 += '1' if not is_tax_invoice else str(is_third_party_invoice)
        ksa_2 += '1' if not is_tax_invoice else str(is_nominal_invoice)
        ksa_2 += str(is_exports_invoice)
        ksa_2 += '1' if not is_tax_invoice else str(is_summary_invoice)
        ksa_2 += "0" if is_exports_invoice else str(is_self_billed_invoice)

        if company_vat and not is_exports_invoice:
            if len(str(self.company_id.vat)) != 15:
                raise exceptions.ValidationError('Vat must be exactly 15 minutes')
            if len(str(self.company_id.vat))[0] != '3' or len(str(self.company_id.vat))[-1] != '3':
                raise exceptions.ValidationError('Vat must start/end with 3')

        document_level_allowance_charge = 0
        vat_tax = 0
        bt_31 = self.company_id.vat
        bg_23_list = {}
        bt_92 = 0  # No document level allowance, in default odoo
        bt_106 = float(round(Decimal(str(0)), 2))  # Sum of bt-131 Calculated in invoice line loop.
        bt_107 = float(round(Decimal(str(bt_92)), 2))
        delivery = 1
        not_know = 0
        bt_81 = 10 if 'cash' else (30 if 'credit' else (42 if 'bank account' else (48 if 'bank card' else 1)))
        if bt_3 == '388':
            bt_81 = 48
        accounting_seller_party = 0
        bt_1 = self.id  # may be name is better
        ubl_2_1 = '''
        <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                 xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">'''
        # if not ksa_13 and signature:  # need to check this
        if signature and not previous_hash:
            ubl_2_1 += '''
            <ext:UBLExtensions>'''
            if signature:
                ubl_2_1 += '''
                <ext:UBLExtension>
                    <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
                    <ext:ExtensionContent>
                        <sig:UBLDocumentSignatures xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2" 
                                                   xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2"
                                                   xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2">
                            <sac:SignatureInformation>
                                <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
                                <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
                                <ds:Signature Id="signature" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'''
                ubl_2_1 += signature
                ubl_2_1 += signature_certificate
                ubl_2_1 += '''  </ds:Signature>
                            </sac:SignatureInformation>
                        </sig:UBLDocumentSignatures>
                    </ext:ExtensionContent>
                </ext:UBLExtension>      '''
            ubl_2_1 += '''
            </ext:UBLExtensions>'''
        if not previous_hash:
            ubl_2_1 += '''
                <cbc:UBLVersionID>2.1</cbc:UBLVersionID>'''
        ubl_2_1 += '''
            <cbc:ProfileID>reporting:1.0</cbc:ProfileID>
            <cbc:ID>''' + str(bt_1) + '''</cbc:ID>
            <cbc:UUID>''' + self.invoice_uuid + '''</cbc:UUID>
            <cbc:IssueDate>''' + self.datetime_field.strftime('%Y-%m-%d') + '''</cbc:IssueDate>
            <cbc:IssueTime>''' + self.datetime_field.strftime('%H:%M:%SZ') + '''</cbc:IssueTime>
            <cbc:DueDate>''' + self.invoice_date_due.strftime('%Y-%m-%d') + '''</cbc:DueDate>
            <cbc:InvoiceTypeCode name="''' + ksa_2 + '''">''' + bt_3 + '''</cbc:InvoiceTypeCode>
            <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>
            <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>'''
        if self.purchase_id.id:
            ubl_2_1 += '''
            <cac:OrderReference>
                <cbc:ID>''' + str(self.purchase_id) + '''</cbc:ID>
            </cac:OrderReference>'''
        if bt_3 != '388':  # BR-KSA-56
            bt_25 = str(self.ref.replace('Reversal of: ', '')[0: self.ref.replace('Reversal of: ', '').find(',')])
            bt_25 = self.env['account.move'].search([('name', '=', bt_25)])
            ubl_2_1 += '''
            <cac:BillingReference>
                <cac:InvoiceDocumentReference>
                    <cbc:ID>''' + str(bt_25.id) + '''</cbc:ID>
                    <cbc:IssueDate>''' + str(bt_25.datetime_field.strftime('%Y-%m-%d')) + '''</cbc:IssueDate>
                </cac:InvoiceDocumentReference>
            </cac:BillingReference>'''
        ubl_2_1 += '''
            <cac:AdditionalDocumentReference>
                <cbc:ID>ICV</cbc:ID>
                <cbc:UUID>''' + str(ksa_16) + '''</cbc:UUID>
            </cac:AdditionalDocumentReference>
            <cac:AdditionalDocumentReference>
                <cbc:ID>PIH</cbc:ID>
                <cac:Attachment>
                    <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">''' + str(ksa_13) + '''</cbc:EmbeddedDocumentBinaryObject>
                </cac:Attachment>
            </cac:AdditionalDocumentReference>'''
        # <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">''' + str(self.l10n_sa_qr_code_str) + '''</cbc:EmbeddedDocumentBinaryObject>

        if not previous_hash:
            ubl_2_1 += '''<cac:AdditionalDocumentReference>
                <cbc:ID>QR</cbc:ID>
                <cac:Attachment>
                    <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">''' + str(self.decoded_data) + '''</cbc:EmbeddedDocumentBinaryObject>
                </cac:Attachment>
            </cac:AdditionalDocumentReference>'''
        if not previous_hash:
            if signature:  # BR-KSA-60
                ubl_2_1 += '''
            <cac:Signature>
                <cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>
                <cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod>
            </cac:Signature>'''
        ubl_2_1 += '''
            <cac:AccountingSupplierParty>
                <cac:Party>'''
        ubl_2_1 += '''
                    <cac:PartyIdentification>
                        <cbc:ID schemeID="''' + self.company_id.license + '''">''' + self.company_id.license_no + '''</cbc:ID>
                    </cac:PartyIdentification>
                    <cac:PostalAddress>
                        <cbc:StreetName>''' + self.company_id.street + '''</cbc:StreetName>'''
        if self.company_id.street2:
            ubl_2_1 += '''
                        <cbc:AdditionalStreetName>''' + self.company_id.street2 + '''</cbc:AdditionalStreetName>'''
        if len(str(self.company_id.additional_no)) != 4:
            raise exceptions.ValidationError('Company/Seller Additional Number must be exactly 4 digits')
        if len(str(self.company_id.zip)) != 5:
            raise exceptions.ValidationError('Company/Seller PostalZone/Zip must be exactly 5 digits')
        ubl_2_1 += '''  <cbc:BuildingNumber>''' + str(self.company_id.building_no) + '''</cbc:BuildingNumber>
                        <cbc:PlotIdentification>''' + str(self.company_id.additional_no) + '''</cbc:PlotIdentification>
                        <cbc:CitySubdivisionName>''' + self.company_id.district + '''</cbc:CitySubdivisionName>
                        <cbc:CityName>''' + self.company_id.city + '''</cbc:CityName>
                        <cbc:PostalZone>''' + str(self.company_id.zip) + '''</cbc:PostalZone>
                        <cbc:CountrySubentity>''' + self.company_id.state_id.name + '''</cbc:CountrySubentity>
                        <cac:Country>
                            <cbc:IdentificationCode>''' + self.company_id.country_id.code + '''</cbc:IdentificationCode>
                        </cac:Country>
                    </cac:PostalAddress>
                    <cac:PartyTaxScheme>
                        <cbc:CompanyID>''' + bt_31 + '''</cbc:CompanyID>
                        <cac:TaxScheme>
                            <cbc:ID>VAT</cbc:ID>
                        </cac:TaxScheme>
                    </cac:PartyTaxScheme>
                    <cac:PartyLegalEntity>
                        <cbc:RegistrationName>''' + self.company_id.name + '''</cbc:RegistrationName>
                    </cac:PartyLegalEntity>
                </cac:Party>
            </cac:AccountingSupplierParty>
            <cac:AccountingCustomerParty>
                <cac:Party>
                    <cac:PartyIdentification>
                        <cbc:ID schemeID="''' + self.partner_id.buyer_identification + '''">''' + self.partner_id.buyer_identification_no + '''</cbc:ID>
                    </cac:PartyIdentification>'''
        if is_tax_invoice:  # Not applicable for simplified tax invoices and associated credit notes and debit notes
            ubl_2_1 += '''
                    <cac:PostalAddress>
                        <cbc:StreetName>''' + self.partner_id.street + '''</cbc:StreetName>'''
            if self.partner_id.street2:
                ubl_2_1 += '''
                        <cbc:AdditionalStreetName>''' + self.partner_id.street2 + '''</cbc:AdditionalStreetName>'''
            ubl_2_1 += '''
                        <cbc:BuildingNumber>''' + str(self.partner_id.building_no) + '''</cbc:BuildingNumber>'''
            if self.partner_id.additional_no:
                ubl_2_1 += '''
                        <cbc:PlotIdentification>''' + str(self.partner_id.additional_no) + '''</cbc:PlotIdentification>'''
            ubl_2_1 += '''
                        <cbc:CitySubdivisionName>''' + self.partner_id.district + '''</cbc:CitySubdivisionName>
                        <cbc:CityName>''' + self.partner_id.city + '''</cbc:CityName>
                        <cbc:PostalZone>''' + str(self.partner_id.zip) + '''</cbc:PostalZone>
                        <cbc:CountrySubentity>''' + self.partner_id.state_id.name + '''</cbc:CountrySubentity>
                        <cac:Country>
                            <cbc:IdentificationCode>''' + self.partner_id.country_id.code + '''</cbc:IdentificationCode>
                        </cac:Country>
                    </cac:PostalAddress>
                    <cac:PartyTaxScheme>'''
            if self.partner_id.vat and not is_exports_invoice:  # BR-KSA-46
                ubl_2_1 += '''
                        <cbc:CompanyID>''' + self.partner_id.vat + '''</cbc:CompanyID>'''
            ubl_2_1 += '''
                        <cac:TaxScheme>
                            <cbc:ID>VAT</cbc:ID>
                        </cac:TaxScheme>
                    </cac:PartyTaxScheme>'''
        bt_121 = 0  # in ['VATEX-SA-EDU', 'VATEX-SA-HEA']
        # BR-KSA-25 and BR-KSA-42
        if is_tax_invoice or ((not is_tax_invoice or ksa_2) and bt_121) or \
                (not is_tax_invoice and is_summary_invoice):
            ubl_2_1 += '''
                    <cac:PartyLegalEntity>
                        <cbc:RegistrationName>''' + self.partner_id.name + '''</cbc:RegistrationName>
                    </cac:PartyLegalEntity>'''
        if bt_121 in ['VATEX-SA-EDU', 'VATEX-SA-HEA'] and self.partner_id.buyer_identification != 'NAT':  #BR-KSA-49
            message = "As tax exemption reason code is in 'VATEX-SA-EDU', 'VATEX-SA-HEA'"
            message += " then Buyer Identification must be 'NAT'"
            raise exceptions.ValidationError(message)
        ubl_2_1 += '''
                </cac:Party>
            </cac:AccountingCustomerParty>'''
        latest_delivery_date = 1 if not is_tax_invoice and is_summary_invoice else 0
        if delivery and ((bt_3 == '388' and ksa_2[:2] == '01' or not is_tax_invoice and is_summary_invoice) or (latest_delivery_date and not_know)):
            ubl_2_1 += '''
            <cac:Delivery>'''
            ksa_5 = self.l10n_sa_delivery_date
            if bt_3 == '388' and ksa_2[:2] == '01' or not is_tax_invoice and is_summary_invoice:
                ubl_2_1 += '''
                <cbc:ActualDeliveryDate>''' + str(ksa_5.strftime('%Y-%m-%d')) + '''</cbc:ActualDeliveryDate>'''
            if latest_delivery_date and not_know:
                ksa_24 = self.l10n_sa_delivery_date
                if ksa_24 < ksa_5:
                    raise exceptions.ValidationError('LatestDeliveryDate must be less then or equal to ActualDeliveryDate')
                ubl_2_1 += '''
                <cbc:LatestDeliveryDate> ''' + str(ksa_24.strftime('%Y-%m-%d')) + ''' </cbc:LatestDeliveryDate> '''
            if not_know:
                ubl_2_1 += '''
                <cac:DeliveryLocation>
                    <cac:Address>
                        <cac:Country>
                            <cbc:IdentificationCode>''' + "" + '''</cbc:IdentificationCode>
                        </cac:Country>
                    </cac:Address>
                </cac:DeliveryLocation'''
            ubl_2_1 += '''
            </cac:Delivery>'''
        if is_tax_invoice or bt_3 != '388':
            ubl_2_1 += '''<cac:PaymentMeans>'''
            if is_tax_invoice:
                ubl_2_1 += '''
                <cbc:PaymentMeansCode>''' + str(bt_81) + '''</cbc:PaymentMeansCode>'''
            if bt_3 != '388':
                ubl_2_1 += '''
                <cbc:InstructionNote>''' + str(self.credit_debit_reason) + '''</cbc:InstructionNote>'''
            ubl_2_1 += '''
            </cac:PaymentMeans>'''
        if document_level_allowance_charge:
            bt_96 = float(round(Decimal(str(0)), 2))
            bt_96 = 100 if bt_96 > 100 else (0 if bt_96 < 0 else bt_96)
            ubl_2_1 += '''
            <cac:AllowanceCharge>
                <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
                <cbc:AllowanceChargeReason>Discount</cbc:AllowanceChargeReason>
                <cbc:Amount currencyID="SAR">''' + str(bt_92) + '''</cbc:Amount>
                <cbc:BaseAmount currencyID="SAR">''' + str(bt_92) + '''</cbc:BaseAmount>
                <cac:TaxCategory>
                    <cbc:ID>''' + "0" + '''</cbc:ID>
                    <cbc:Percent>''' + str(bt_96) + '''</cbc:Percent>
                    <cac:TaxScheme>
                        <cbc:ID>''' + "0" + '''</cbc:ID>
                    </cac:TaxScheme>
                </cac:TaxCategory>
            </cac:AllowanceCharge>'''
        invoice_line_xml = ''
        for invoice_line_id in self.invoice_line_ids:
            if invoice_line_id.discount:
                bt_137 = float(round(Decimal(str(invoice_line_id.price_unit * invoice_line_id.quantity)), 2))
                bt_138 = invoice_line_id.discount  # BR-KSA-DEC-01 for BT-138 only done
                bt_136 = float(round(Decimal(str(bt_137 * bt_138 / 100)), 2))
            else:
                bt_136 = float(round(Decimal(str(0)), 2))
                bt_137 = float(round(Decimal(str(0)), 2))
                bt_138 = invoice_line_id.discount  # BR-KSA-DEC-01 for BT-138 only done
            bt_129 = invoice_line_id.quantity
            bt_147 = 0  # NO ITEM PRICE DISCOUNT bt_148 * invoice_line_id.discount/100 if invoice_line_id.discount else 0
            bt_148 = invoice_line_id.price_unit
            bt_146 = bt_148 - bt_147
            bt_149 = 1  # ??
            bt_131 = float(round(Decimal(str(((bt_146 / bt_149) * bt_129))), 2))
            bt_131 -= float(round(Decimal(str(bt_136)), 2))
            bt_131 = float(round(Decimal(str(bt_131)), 2))
            bt_106 += float(round(Decimal(str(bt_131)), 2))
            bt_106 = float(round(Decimal(str(bt_106)), 2))
            bt_151 = invoice_line_id.tax_ids.classified_tax_category if invoice_line_id.tax_ids else "O"
            bt_152 = float(round(Decimal(str(invoice_line_id.tax_ids.amount)), 2)) if invoice_line_id.tax_ids else 0
            bt_152 = 100 if bt_152 > 100 else (0 if bt_152 < 0 else bt_152)

            if bt_151 == "Z":
                bt_152 = 0
                if not bg_23_list.get("Z", False):
                    bg_23_list["Z"] = {'bt_116': 0, 'bt_121': invoice_line_id.tax_ids.tax_exemption_code,
                                       'bt_120': invoice_line_id.tax_ids.tax_exemption_text,
                                       'bt_119': bt_152, 'bt_117': 0}
                bg_23_list["Z"]['bt_116'] += bt_131
                # bg_23_list = ["Z"]  # BR-Z-01
            elif bt_151 == "E":
                bt_152 = 0
                if not bg_23_list.get("E", False):
                    bg_23_list["E"] = {'bt_116': 0, 'bt_121': invoice_line_id.tax_ids.tax_exemption_code,
                                       'bt_120': invoice_line_id.tax_ids.tax_exemption_text,
                                       'bt_119': bt_152, 'bt_117': 0}
                bg_23_list["E"]['bt_116'] += bt_131
                # bg_23_list = ["E"]  # BR-E-01
            elif bt_151 == "S":
                if not bg_23_list.get("S", False):
                    bg_23_list["S"] = {'bt_116': 0, 'bt_119': bt_152, 'bt_117': 0}
                bg_23_list["S"]['bt_116'] += bt_131
                # bg_23_list = ["E"]  # BR-S-09
            elif bt_151 == "O":
                bt_152 = 0
                if not bg_23_list.get("O", False):
                    bg_23_list["O"] = {'bt_116': 0, 'bt_121': 'Not subject to VAT',
                                       'bt_120': 'Not subject to VAT', 'bt_119': 0, 'bt_117': 0}
                bg_23_list["O"]['bt_116'] += bt_131
                # bg_23_list = ["O"]  # BR-O-01

            invoice_line_xml += '''
            <cac:InvoiceLine>
                <cbc:ID>''' + str(invoice_line_id.id) + '''</cbc:ID>
                <cbc:InvoicedQuantity unitCode="PCE">''' + str(bt_129) + '''</cbc:InvoicedQuantity>
                <cbc:LineExtensionAmount currencyID="SAR">''' + str(bt_131) + '''</cbc:LineExtensionAmount>'''
            if invoice_line_id.discount: #line_allowance_charge:
                invoice_line_xml += '''
                <cac:AllowanceCharge>
                    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
                    <cbc:AllowanceChargeReasonCode>95</cbc:AllowanceChargeReasonCode>
                    <cbc:AllowanceChargeReason>Discount</cbc:AllowanceChargeReason>'''
                # invoice_line_xml += '''
                #     <cbc:MultiplierFactorNumeric>''' + str(bt_138) + '''</cbc:MultiplierFactorNumeric>'''
                invoice_line_xml += '''
                    <cbc:Amount currencyID="SAR">''' + str(bt_136) + '''</cbc:Amount>'''
                # invoice_line_xml += '''
                #     <cbc:BaseAmount currencyID="SAR">''' + str(bt_137) + '''</cbc:BaseAmount>'''
                if bt_151 != 'O':
                    invoice_line_xml += '''
                        <cac:TaxCategory>
                            <cbc:ID>S</cbc:ID>
                            <cbc:Percent>15</cbc:Percent>
                            <cac:TaxScheme>
                                <cbc:ID>VAT</cbc:ID>
                            </cac:TaxScheme>
                        </cac:TaxCategory>'''
                invoice_line_xml += '''
                    </cac:AllowanceCharge>'''
            ksa_11 = float(round(Decimal(str(bt_131 * bt_152/100)), 2))  #BR-KSA-50
            ksa_12 = float(round(Decimal(str(bt_131 + ksa_11)), 2))  # BR-KSA-51
            if is_tax_invoice:
                invoice_line_xml += '''
                <cac:TaxTotal>'''
                if is_tax_invoice:  #BR-KSA-52 and BR-KSA-53
                    invoice_line_xml += '''
                    <cbc:TaxAmount currencyID="SAR">''' + str(ksa_11) + '''</cbc:TaxAmount>
                    <cbc:RoundingAmount currencyID="SAR">''' + str(ksa_12) + '''</cbc:RoundingAmount>'''
                invoice_line_xml += '''
                </cac:TaxTotal>'''
            invoice_line_xml += '''
                <cac:Item>
                    <cbc:Name>''' + str(invoice_line_id.product_id.name) + '''</cbc:Name>'''
            if invoice_line_id.product_id.barcode and invoice_line_id.product_id.code_type:
                invoice_line_xml += '''
                    <cac:StandardItemIdentification>
                        <cbc:ID schemeID="''' + str(invoice_line_id.product_id.code_type) + '''">''' + str(invoice_line_id.product_id.barcode) + '''</cbc:ID>
                    </cac:StandardItemIdentification>'''
            invoice_line_xml += '''
                    <cac:ClassifiedTaxCategory>
                        <cbc:ID>''' + str(bt_151) + '''</cbc:ID>'''
            if bt_151 != 'O':
                invoice_line_xml += '''
                        <cbc:Percent>''' + str(bt_152) + '''</cbc:Percent>'''
            invoice_line_xml += '''
                        <cac:TaxScheme>
                            <cbc:ID>VAT</cbc:ID>
                        </cac:TaxScheme>
                    </cac:ClassifiedTaxCategory>
                </cac:Item>
                <cac:Price>
                    <cbc:PriceAmount currencyID="SAR">''' + str(bt_146) + '''</cbc:PriceAmount>
                    <cbc:BaseQuantity unitCode="PCE">''' + str(bt_149) + '''</cbc:BaseQuantity>
                </cac:Price>
            </cac:InvoiceLine>'''
        bt_110 = float(round(Decimal(str(0)), 2))  # Sum of bt-117 Calculated in bg_23 loop
        tax_subtotal_xml = ''
        for bg_23 in bg_23_list.keys():
            bt_116 = float(round(Decimal(str(bg_23_list[bg_23]['bt_116'])), 2))
            bt_119 = bg_23_list[bg_23]['bt_119']
            bt_118 = bg_23
            if bt_118 == "S":
                bt_117 = float(round(Decimal(str(bt_116 * (bt_119 / 100))), 2))
                bt_110 += bt_117
            else:
                bt_117 = float(round(Decimal(str(0)), 2))
            tax_subtotal_xml += '''
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="SAR">''' + str(bt_116) + '''</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="SAR">''' + str(bt_117) + '''</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:ID>''' + str(bt_118) + '''</cbc:ID>'''
            if bt_118 != "O":
                tax_subtotal_xml += '''
                    <cbc:Percent>''' + str(bt_119) + '''</cbc:Percent>'''
            if bt_118 != "S" and bt_118 in ['E', 'O', 'Z']:
                bt_120 = bg_23_list[bg_23]['bt_120']
                bt_121 = bg_23_list[bg_23]['bt_121']
                tax_subtotal_xml += '''
                    <cbc:TaxExemptionReasonCode>''' + str(bt_121) + '''</cbc:TaxExemptionReasonCode>
                    <cbc:TaxExemptionReason>''' + str(bt_120) + '''</cbc:TaxExemptionReason>'''
            tax_subtotal_xml += '''
                    <cac:TaxScheme>
                        <cbc:ID>VAT</cbc:ID>
                    </cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>'''
        bt_109 = float(round(Decimal(str(bt_106 - bt_107)), 2))
        bt_111 = bt_110  # Same as bt-110
        bt_112 = float(round(Decimal(str(bt_109 + bt_110)), 2))
        bt_113 = float(round(Decimal(str(self.amount_total - self.amount_residual)), 2))
        bt_115 = float(round(Decimal(str(bt_112 - bt_113)), 2))
        ubl_2_1 += '''
            <cac:TaxTotal>
                <cbc:TaxAmount currencyID="SAR">''' + str(bt_110) + '''</cbc:TaxAmount>'''
        ubl_2_1 += tax_subtotal_xml
        ubl_2_1 += '''
            </cac:TaxTotal>
            <cac:TaxTotal>
                <cbc:TaxAmount currencyID="SAR">''' + str(bt_111) + '''</cbc:TaxAmount>
            </cac:TaxTotal>'''
        ubl_2_1 += '''
            <cac:LegalMonetaryTotal>
                <cbc:LineExtensionAmount currencyID="SAR">''' + str(bt_106) + '''</cbc:LineExtensionAmount>
                <cbc:TaxExclusiveAmount currencyID="SAR">''' + str(bt_109) + (" | " + str(self.amount_untaxed) if amount_verification else '') +'''</cbc:TaxExclusiveAmount>
                <cbc:TaxInclusiveAmount currencyID="SAR">''' + str(bt_112) + (" | " + str(self.amount_total) if amount_verification else '') + '''</cbc:TaxInclusiveAmount>'''
        if not_know:
            ubl_2_1 += '''
                <cbc:ChargeTotalAmount currencyID="SAR">''' + str("0") + '''</cbc:ChargeTotalAmount>'''
        if bt_113:
            ubl_2_1 += '''
                <cbc:PrepaidAmount currencyID="SAR">''' + str(bt_113) + '''</cbc:PrepaidAmount>'''
        if not_know:
            ubl_2_1 += '''
                <cbc:PayableRoundingAmount currencyID="SAR">''' + str("0") + '''</cbc:PayableRoundingAmount>'''
        ubl_2_1 += '''
                <cbc:PayableAmount currencyID="SAR">''' + str(bt_115 if bt_115 > 0 else 0) + (" | " + str(self.amount_residual) if amount_verification else '') + '''</cbc:PayableAmount>
            </cac:LegalMonetaryTotal>'''
        ubl_2_1 += invoice_line_xml
        ubl_2_1 += '''
        </Invoice>'''

        file_name_specification = str(bt_31) + "_" + self.datetime_field.strftime('%Y%m%d') + "T" + self.datetime_field.strftime('%H%M%SZ') + "_" + str(self.id)
        self.zatca_invoice_name = file_name_specification + ".xml"
        self.hash_with_c14n_canonicalization(xml=ubl_2_1)
        # zatca_invoice_hash
        ubl_2_1 = ubl_2_1.replace('zatca_invoice_hash', str(self.zatca_invoice_hash))

        atts = self.env['ir.attachment'].sudo().search([('res_model', '=', 'account.move'), ('res_field', '=', 'zatca_invoice'),
                                                        ('res_id', 'in', self.ids)])
        # self.xml_sign_char_data = ubl_2_1
        self.xml_sign_char_data = ubl_2_1
        if atts:
            atts.sudo().write({'datas': base64.b64encode(bytes(ubl_2_1, 'utf-8'))})
        else:
            atts.sudo().create([{
                'name': file_name_specification + ".xml",
                'res_model': 'account.move',
                'res_field': 'zatca_invoice',
                'res_id': self.id,
                'type': 'binary',
                'datas': base64.b64encode(bytes(ubl_2_1, 'utf-8')),
                'mimetype': 'text/xml',
                # 'datas_fname': file_name_specification + ".xml"
            }])
        print("ZATCA: xml invoice & hash invoice generated.")

    def generate_signature(self):
        # STEP # 1 => DONE  => NOT NEEDED, DONE ABOVE
        # STEP # 2
        # hash = xQ93zdUB9jwWLb7Oy1uPeKKAlmkaGfZHmEOWU7xvHvE=
        f = open('zatcaprivatekey.pem', 'r')
        private_key = f.read()
        digital_signature = '?'
        # STEP # 3 => DONE  => NOT NEEDED, DONE ABOVE
        # STEP # 4 => DONE  => NOT NEEDED, DONE ABOVE
        # STEP # 5
        # STEP # 6 => Partially DONE

    def compliance_invoices_api(self):
        # link = "https://gw-apic-gov.gazt.gov.sa/e-invoicing/developer-portal"
        # endpoint = '/compliance/invoices'

        link = self.env['zatca.einvoice.configuration'].search([('company_id','=',self.env.user.company_id.id)]).compliance_url

        conf = self.env['ir.config_parameter'].sudo()

        user = conf.get_param("zatca_sb_bsToken", False)
        password = conf.get_param("zatca_sb_secret", False)
        auth = base64.b64encode(('%s:%s' % (user, password)).encode('utf-8')).decode('utf-8')
        headers = {'accept': 'application/json',
                   'Accept-Language': 'en',
                   'Accept-Version': 'V2',
                   'Authorization': 'Basic ' + auth,
                   'Content-Type': 'application/json'}

        data = {
            'invoiceHash': self.zatca_invoice_hash,
            # 'invoiceHash': self.hash_with_c14n_canonicalization(api_invoice=1),
            'uuid': self.invoice_uuid,
            'invoice': self.zatca_invoice.decode('UTF-8'),
        }
        try:
            # req = requests.post(link + endpoint, headers=headers, data=json.dumps(data))
            req = requests.post(link, headers=headers, data=json.dumps(data))
            if req.status_code == 500:
                raise exceptions.AccessError('Invalid Request, \ncontact system administer')
            elif req.status_code == 401:
                raise exceptions.AccessError('Unauthorized Request, \nUpdate configuration for sandbox')
            elif req.status_code in [200, 400]:
                response = json.loads(req.text)
                string = "<table style='width:100%'>"
                string += "<tr><td  colspan='6'><b>validationResults</b></td></tr>"

                for key, value in response['validationResults'].items():
                    if type(value) == list:
                        string += "<tr><td  colspan='6'><center><b>" + key + "</b></center></td></tr>"
                        qty = 1
                        for val in value:
                            color = 'green' if str(val['status']).lower() == 'pass' else 'red'
                            string += "<tr>"
                            string += "<td colspan='2' style='border: 1px solid black;'>" + str(qty) + "</td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'type' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'code' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'category' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'status' + "</b></td>"
                            string += "</tr>"
                            string += "<tr>"
                            string += "<td  style='border: 1px solid black;' colspan='2'></td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['type']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['code']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['category']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['status']) + "</td>"
                            string += "</tr>"
                            string += "<tr>"
                            string += "<td colspan='2'  style='border: 1px solid black;'><b>" + 'message' + "</b></td>"
                            string += "<td colspan='4'  style='border: 1px solid black;color: " + color + ";'>" + str(val['message']) + "</td>"
                            string += "</tr>"
                            qty += 1
                    else:
                        string += "<tr>"
                        string += "<td>" + key + "</td><td colspan='3'>" + str(value) + "</td>"
                        string += "</tr>"
                string += "<tr><td colspan='2'><b>reportingStatus</b></td><td colspan='4'>" + str(response['reportingStatus']) + "</td></tr>"
                string += "<tr><td colspan='2'><b>clearanceStatus</b></td><td colspan='4'>" + str(response['clearanceStatus']) + "</td></tr>"
                string += "<tr><td colspan='2'><b>qrSellertStatus</b></td><td colspan='4'>" + str(response['qrSellertStatus']) + "</td></tr>"
                string += "<tr><td colspan='2'><b>qrBuyertStatus </b></td><td colspan='4'>" + str(response['qrBuyertStatus'])+ "</td></tr>"
                string += "</table>"

                json_iterated = string
                self.zatca_compliance_invoices_api = json_iterated
            return {
                'type': 'ir.actions.act_window',
                'name': "acv",
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': self.id,
                'views': [(self.env.ref('invoice_zatca_integrations.zatca_response').id, 'form')],
            }
        except Exception as e:
            raise exceptions.AccessDenied(e)

    def invoices_clearance_single_api(self):
        # link = "https://gw-apic-gov.gazt.gov.sa/e-invoicing/developer-portal"
        # endpoint = '/invoices/clearance/single'

        link = self.env['zatca.einvoice.configuration'].search([('company_id','=',self.env.user.company_id.id)]).clearance_url



        conf = self.env['ir.config_parameter'].sudo()

        user = conf.get_param("zatca_bsToken", False)
        password = conf.get_param("zatca_secret", False)
        auth = base64.b64encode(('%s:%s' % (user, password)).encode('utf-8')).decode('utf-8')
        headers = {'accept': 'application/json',
                   'Accept-Language': 'en',
                   'Clearance-Status': '1',
                   'Accept-Version': 'V2',
                   'Authorization': 'Basic ' + auth,
                   'Content-Type': 'application/json'}

        data = {
            'invoiceHash': self.zatca_invoice_hash,
            # 'invoiceHash': self.hash_with_c14n_canonicalization(api_invoice=1),
            'uuid': self.invoice_uuid,
            'invoice': self.zatca_invoice.decode('UTF-8'),
        }
        try:
            # req = requests.post(link + endpoint, headers=headers, data=json.dumps(data))
            req = requests.post(link, headers=headers, data=json.dumps(data))
            if req.status_code == 500:
                raise exceptions.AccessError('Invalid Request, \ncontact system administer')
            elif req.status_code == 401:
                raise exceptions.AccessError('Unauthorized Request, \nUpdate configuration for production')
            elif req.status_code in [200, 400]:
                response = json.loads(req.text)
                string = "<table style='width:100%'>"
                string += "<tr><td  colspan='6'><b>validationResults</b></td></tr>"

                for key, value in response['validationResults'].items():
                    if type(value) == list:
                        string += "<tr><td  colspan='6'><center><b>" + key + "</b></center></td></tr>"
                        qty = 1
                        for val in value:
                            color = 'green' if str(val['status']).lower() == 'pass' else 'red'
                            string += "<tr>"
                            string += "<td colspan='2' style='border: 1px solid black;'>" + str(qty) + "</td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'type' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'code' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'category' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'status' + "</b></td>"
                            string += "</tr>"
                            string += "<tr>"
                            string += "<td  style='border: 1px solid black;' colspan='2'></td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['type']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['code']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['category']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['status']) + "</td>"
                            string += "</tr>"
                            string += "<tr>"
                            string += "<td colspan='2'  style='border: 1px solid black;'><b>" + 'message' + "</b></td>"
                            string += "<td colspan='4'  style='border: 1px solid black;color: " + color + ";'>" + str(val['message']) + "</td>"
                            string += "</tr>"
                            qty += 1
                    else:
                        string += "<tr>"
                        string += "<td>" + key + "</td><td colspan='3'>" + str(value) + "</td>"
                        string += "</tr>"
                string += "<tr><td colspan='2'><b>clearanceStatus</b></td><td colspan='4'>" + str(response['clearanceStatus']) + "</td></tr>"
                string += "<tr><td colspan='2'><b>clearedInvoice</b></td><td colspan='4'>" + str(response['clearedInvoice']) + "</td></tr>"
                string += "</table>"

                json_iterated = string
                self.zatca_compliance_invoices_api = json_iterated

                file_name_specification = str(self.company_id.vat) + "_" + self.datetime_field.strftime('%Y%m%d') + "T" + self.datetime_field.strftime('%H%M%SZ') + "_" + str(self.id)
                atts = self.env['ir.attachment'].sudo().search([('res_model', '=', 'account.move'),
                                                                ('res_field', '=', 'zatca_hash_cleared_invoice'),
                                                                ('res_id', 'in', self.ids)])
                if response['clearedInvoice']:
                    if atts:
                        atts.sudo().write({'datas': base64.b64encode(bytes(response['clearedInvoice'], 'utf-8'))})
                    else:
                        atts.sudo().create([{
                            'name': file_name_specification + 'cleared' + ".xml",
                            'res_model': 'account.move',
                            'res_field': 'zatca_hash_cleared_invoice',
                            'res_id': self.id,
                            'type': 'binary',
                            'datas': base64.b64encode(bytes(response['clearedInvoice'], 'utf-8')),
                            'mimetype': 'text/xml',
                        }])
                    self.zatca_hash_cleared_invoice_name = file_name_specification + 'hash' + ".xml"
            return {
                'type': 'ir.actions.act_window',
                'name': "acv",
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': self.id,
                'views': [(self.env.ref('invoice_zatca_integrations.zatca_response').id, 'form')],
            }
        except Exception as e:
            raise exceptions.AccessDenied(e)

    def invoices_reporting_single_api(self):
        # link = "https://gw-apic-gov.gazt.gov.sa/e-invoicing/developer-portal"
        # endpoint = '/invoices/reporting/single'

        link = self.env['zatca.einvoice.configuration'].search([('company_id','=',self.env.user.company_id.id)]).reporting_url


        conf = self.env['ir.config_parameter'].sudo()

        user = conf.get_param("zatca_bsToken", False)
        password = conf.get_param("zatca_secret", False)
        auth = base64.b64encode(('%s:%s' % (user, password)).encode('utf-8')).decode('utf-8')
        headers = {'accept': 'application/json',
                   'Accept-Language': 'en',
                   'Clearance-Status': '1',
                   'Accept-Version': 'V2',
                   'Authorization': 'Basic ' + auth,
                   'Content-Type': 'application/json'}

        data = {
            'invoiceHash': self.zatca_invoice_hash,
            # 'invoiceHash': self.hash_with_c14n_canonicalization(api_invoice=1),
            'uuid': self.invoice_uuid,
            'invoice': self.zatca_invoice.decode('UTF-8'),
        }
        try:
            # req = requests.post(link + endpoint, headers=headers, data=json.dumps(data))
            req = requests.post(link, headers=headers, data=json.dumps(data))
            if req.status_code == 500:
                raise exceptions.AccessError('Invalid Request, \ncontact system administer')
            elif req.status_code == 401:
                raise exceptions.AccessError('Unauthorized Request, \nUpdate configuration for production')
            elif req.status_code in [200, 400]:
                response = json.loads(req.text)
                string = "<table style='width:100%'>"
                string += "<tr><td  colspan='6'><b>validationResults</b></td></tr>"

                for key, value in response['validationResults'].items():
                    if type(value) == list:
                        string += "<tr><td  colspan='6'><center><b>" + key + "</b></center></td></tr>"
                        qty = 1
                        for val in value:
                            color = 'green' if str(val['status']).lower() == 'pass' else 'red'
                            string += "<tr>"
                            string += "<td colspan='2' style='border: 1px solid black;'>" + str(qty) + "</td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'type' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'code' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'category' + "</b></td>"
                            string += "<td  style='border: 1px solid black;'><b>" + 'status' + "</b></td>"
                            string += "</tr>"
                            string += "<tr>"
                            string += "<td  style='border: 1px solid black;' colspan='2'></td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['type']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['code']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['category']) + "</td>"
                            string += "<td  style='border: 1px solid black;color: " + color + ";'>" + str(val['status']) + "</td>"
                            string += "</tr>"
                            string += "<tr>"
                            string += "<td colspan='2'  style='border: 1px solid black;'><b>" + 'message' + "</b></td>"
                            string += "<td colspan='4'  style='border: 1px solid black;color: " + color + ";'>" + str(val['message']) + "</td>"
                            string += "</tr>"
                            qty += 1
                    else:
                        string += "<tr>"
                        string += "<td>" + key + "</td><td colspan='3'>" + str(value) + "</td>"
                        string += "</tr>"
                string += "<tr><td colspan='2'><b>reportingStatus</b></td><td colspan='4'>" + str(response['reportingStatus']) + "</td></tr>"
                string += "</table>"

                json_iterated = string
                self.zatca_compliance_invoices_api = json_iterated
            return {
                'type': 'ir.actions.act_window',
                'name': "acv",
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': self.id,
                'views': [(self.env.ref('invoice_zatca_integrations.zatca_response').id, 'form')],
            }
        except Exception as e:
            raise exceptions.AccessDenied(e)

    def hash_with_c14n_canonicalization(self, api_invoice=0, xml=0):
        invoice = base64.b64decode(self.zatca_invoice).decode() if not xml else xml
        xml_file = ET.fromstring(invoice)
        if not api_invoice:
            xsl_file = ET.fromstring('''<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                            xmlns:xs="http://www.w3.org/2001/XMLSchema"
                            xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                            xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                            xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                            xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
                            exclude-result-prefixes="xs"
                            version="2.0">
                <xsl:output omit-xml-declaration="yes" encoding="utf-8" indent="no"/>
                <xsl:template match="node() | @*">
                    <xsl:copy>
                        <xsl:apply-templates select="node() | @*"/>
                    </xsl:copy>
                </xsl:template>
                <xsl:template match="//*[local-name()='Invoice']//*[local-name()='UBLExtensions']"></xsl:template>
                <xsl:template match="//*[local-name()='AdditionalDocumentReference'][cbc:ID[normalize-space(text()) = 'QR']]"></xsl:template>
                 <xsl:template match="//*[local-name()='Invoice']/*[local-name()='Signature']"></xsl:template>
            </xsl:stylesheet>''')
            transform = ET.XSLT(xsl_file.getroottree())
            transformed_xml = transform(xml_file.getroottree())
        else:
            transformed_xml = xml_file.getroottree()
        sha256_hash = hashlib.sha256()
        sha256_hash.update(ET.tostring(transformed_xml))
        generated_hash = sha256_hash.hexdigest()
        base64_encoded = base64.b64encode(sha256_hash.digest()).decode()
        if not api_invoice:
            self.zatca_invoice_hash = base64_encoded
        else:
            return base64_encoded

        atts = self.env['ir.attachment'].sudo().search([('res_model', '=', 'account.move'),
                                                        ('res_field', '=', 'zatca_hash_invoice'),
                                                        ('res_id', 'in', self.ids)])
        if atts:
            atts.sudo().write({'datas': base64.b64encode(ET.tostring(transformed_xml))})
        else:
            atts.sudo().create([{
                'name': self.zatca_invoice_name.replace('.xml', '_hash.xml'),
                'res_model': 'account.move',
                'res_field': 'zatca_hash_invoice',
                'res_id': self.id,
                'type': 'binary',
                'datas': base64.b64encode(ET.tostring(transformed_xml)),
                'mimetype': 'text/xml',
            }])
        self.zatca_hash_invoice_name = self.zatca_invoice_name.replace('.xml', '_hash.xml')

