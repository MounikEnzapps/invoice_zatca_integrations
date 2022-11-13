from odoo import api, fields, models, exceptions
from decimal import Decimal
import hashlib
import base64
import uuid


class AccountMove(models.Model):
    _inherit = "account.move"

    zatca_hash_invoice = fields.Binary("ZATCA generated invoice for hash", attachment=True, readonly=1)
    zatca_hash_invoice_name = fields.Char()

    zatca_invoice = fields.Binary("ZATCA generated invoice", attachment=True, readonly=1)
    zatca_invoice_name = fields.Char()
    credit_debit_reason = fields.Char(string="Reasons for issuance of credit / debit note",
                                   help="Reasons as per Article 40 (paragraph 1) of KSA VAT regulations")
    invoice_date = fields.Datetime(string='Invoice/Bill Date', readonly=True, index=True, copy=False,
                                   states={'draft': [('readonly', False)]})

    def create_xml_file(self, previous_hash=0):

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
                                            <ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath>
                                        </ds:Transform>
                                        <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
                                    </ds:Transforms>
                                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                    <ds:DigestValue>tIgyb6RmuRm+rvj8tL5cbwK5eRk=</ds:DigestValue>
                                </ds:Reference>
                                <ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">
                                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                    <ds:DigestValue>skZ+8g6hyUFzbbTZvJZRyAREMiM=</ds:DigestValue>
                                </ds:Reference>
                            </ds:SignedInfo>
                            <ds:SignatureValue>J3dQSz3nEQd8wagH2CBlip1fj03NTccYAQTGiU/4IhBYzylKxjB09OMBb5vXj2Lv7eXhciRoMmvSF+A9eIUd2a4b5aEm7VBkxIbyGgltNHR8u3oZ7Ee+HNWRAQU+IFCKpZoVA68Bo/g4Gy3pqNQoC7AOghUUXTjvFEBcHVgpt/5wDC8U3PwNfx9hzpU00t/b042GyLECGjPDzr8mGbI09mobT7sSb9oPPzxsC71dph+oU0ug+TAh2NheVih+HWCe870hFJvH3mZ9YcC/lcMXb80Ot+LSjgV8gcTSDz/BaOYLjEGvZrOxmoK2doUZNPi811tbq6nC4jjlrU+NRr5kQA==</ds:SignatureValue>
                            <ds:KeyInfo>
                                <ds:X509Data>
                                    <ds:X509Certificate>MIIDaDCCAlCgAwIBAgIKlswlvJ8beIpd9jANBgkqhkiG9w0BAQsFADBiMRkwFwYDVQQDExBNb2hkIEtoYWxpZmEgUDEyMRAwDgYDVQQKEwd0ZXMgcHdjMQkwBwYDVQQLEwAxGzAZBgkqhkiG9w0BCQEWDFRlc3RAcHdjLmNvbTELMAkGA1UEBhMCQUUwHhcNMjEwMjI1MTI1NjU3WhcNMjYwMjI1MTI1NjU3WjBiMRkwFwYDVQQDExBNb2hkIEtoYWxpZmEgUDEyMRAwDgYDVQQKEwd0ZXMgcHdjMQkwBwYDVQQLEwAxGzAZBgkqhkiG9w0BCQEWDFRlc3RAcHdjLmNvbTELMAkGA1UEBhMCQUUwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDWaRBaLHqhlZDDAf+YH2H2xgtHT9tMcg3vmGuP4YT2aeG77RWnIu0bqtNiNrOK+ph7UE+B2ClyW+CRixDx82Qkn9IUX+nw28QO7ux9UBDt3nIeL6euAUPMxrnyESALXXRjTLrJK3p6vsFr3hNbP4V0t/ZDAtk36PAn6WfKZICMI63GnzWLAQz6QOGvVmOYNym93Q84W9Ttn844yfun1EVj/+XC3bYmysTPbAgPZ/vT1UgeolOrvnsEKeDR8w43C1Juuw9CVi3duekYf1WVjfuNNClocjZ0N4D7dYdg536bqtc4F8C6sBmk/2YfG/Fsqb6DSU0FU1dSj+rjZvaR6tIDAgMBAAGjIDAeMA8GCSqGSIb3LwEBCgQCBQAwCwYDVR0PBAQDAgeAMA0GCSqGSIb3DQEBCwUAA4IBAQDACtfjpOtcy5dPp1tS31rB9lJ7aeQ6dayxJGyXGovhjYZ8N60sAR/0Yfe1EkjbFLV25AGw/06jZV7Fy8jK2jR7TJnv2QnxZz4ldg2k8DolC6J4YZqI5R0THFnd09MNHcgV6ChGJNzivRRkTrwFM0qWErTCh/5wA/GHgqRKjWUA/S2P7UbKbjIA5Ba6N3K/zT4DfspxvvCp50jigPyh1e/UilQdexNFUmkUyZBisKEhpdHURHCJY2ip0iH8wZtG4oiGtisLEHJT+ZREWIzjTUKlw9ImXu2e4ptzrPBPLMGdWdQ153YCkXFKLbV97JBUzilUhJ7GouDYKj3PnUzLMCSd</ds:X509Certificate>
                                </ds:X509Data>
                            </ds:KeyInfo>
                            <ds:Object>
                                <xades:QualifyingProperties Target="signature" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">
                                    <xades:SignedProperties Id="xadesSignedProperties">
                                        <xades:SignedSignatureProperties>
                                            <xades:SigningTime>2021-02-25T12:57:51Z</xades:SigningTime>
                                            <xades:SigningCertificate>
                                                <xades:Cert>
                                                    <xades:CertDigest>
                                                        <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                                        <ds:DigestValue>p6/1GNOqntK37JwfUub56vSecg0=</ds:DigestValue>
                                                    </xades:CertDigest>
                                                    <xades:IssuerSerial>
                                                        <ds:X509IssuerName>C=SA,  E=Test@test Taxpayer.com, OU=&quot;&quot;, O=test Taxpayer, CN=EGS0001</ds:X509IssuerName>
                                                        <ds:X509SerialNumber>1234</ds:X509SerialNumber>
                                                    </xades:IssuerSerial>
                                                </xades:Cert>
                                            </xades:SigningCertificate>
                                        </xades:SignedSignatureProperties>
                                    </xades:SignedProperties>
                                </xades:QualifyingProperties>
                            </ds:Object>'''
        # UBL 2.1 sequence
        # Business rules - integrity constraints (BR) page 1 of 3 applied.

        if self.company_id.currency_id.name != 'SAR':
            # BR-KSA-CL-02
            raise exceptions.ValidationError('currency must be SAR')
        if len(self.invoice_line_ids.ids) <= 0:
            raise exceptions.MissingError('at least one invoice line is required.')
        if self.invoice_date > fields.Datetime.today():
            raise exceptions.ValidationError('Date should be less then or equal to today.')
        if not self.company_id.district or not self.company_id.building_no or not self.company_id.additional_no or\
            not self.company_id.city or not self.company_id.zip or not self.company_id.state_id.id or\
                not self.company_id.country_id.id or not self.company_id.street:
            raise exceptions.ValidationError('Some Values are missing in Company Address')

        bt_3 = '383' if self.debit_origin_id.id else ('381' if self.move_type == 'out_refund' else '388')
        is_tax_invoice = 1

        if is_tax_invoice and not self.partner_id.district or not self.partner_id.building_no or\
                not self.partner_id.additional_no or not self.partner_id.city or not self.partner_id.zip or\
                not self.partner_id.state_id.id or not self.partner_id.country_id.id or not\
                self.partner_id.street or not self.partner_id.street2:
            message = 'Some Values are missing in Customer Address, which are required for tax invoices'
            raise exceptions.ValidationError(message)

        ksa_16 = int(self.env['ir.config_parameter'].sudo().get_param('zatca.icv_counter'))
        ksa_16 += 1
        self.env['ir.config_parameter'].sudo().set_param('zatca.icv_counter', str(ksa_16))

        company_vat = 0
        # BR-KSA-26
        ksa_13 = 0
        ksa_13 = base64.b64encode(bytes(hashlib.sha256(str(ksa_13).encode('utf-8')).hexdigest(), encoding='utf-8')).decode('UTF-8')
        # signature = 0 if is_tax_invoice else 1
        is_third_party_invoice = 0
        is_nominal_invoice = 0
        is_exports_invoice = 0
        is_summary_invoice = 0
        is_self_billed_invoice = 0
        # BR-KSA-31 (KSA-2)
        ksa_2 = '01' if is_tax_invoice else '02'
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
        if signature:
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
                ubl_2_1 += '''  </ds:Signature>
                            </sac:SignatureInformation>
                        </sig:UBLDocumentSignatures>
                    </ext:ExtensionContent>
                </ext:UBLExtension>      '''
            ubl_2_1 += '''
            </ext:UBLExtensions>'''
        ubl_2_1 += '''
            <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
bt-23            <cbc:ProfileID>reporting:1.0</cbc:ProfileID>
bt-1            <cbc:ID>''' + str(bt_1) + '''</cbc:ID>
KSA-1                <cbc:UUID>''' + str(str(uuid.uuid4())) + '''</cbc:UUID>
bt-2            <cbc:IssueDate>''' + self.invoice_date.strftime('%Y-%m-%d') + '''</cbc:IssueDate>
bt-25-ok            <cbc:IssueTime>''' + self.invoice_date.strftime('%H:%M:%SZ') + '''</cbc:IssueTime>
bt-?            <cbc:DueDate>''' + self.invoice_date_due.strftime('%Y-%m-%d') + '''</cbc:DueDate>
bt-3            <cbc:InvoiceTypeCode name="''' + ksa_2 + '''">''' + bt_3 + '''</cbc:InvoiceTypeCode>

bt-5            <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>
bt-6-ok            <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>'''
        if self.purchase_id.id:
            ubl_2_1 += '''
            <cac:OrderReference>
bt-13                    <cbc:ID>''' + str(self.purchase_id) + '''</cbc:ID>
            </cac:OrderReference>'''
        if bt_3 != '388':  # BR-KSA-56
            bt_25 = str(self.ref.replace('Reversal of: ', '')[0: self.ref.replace('Reversal of: ', '').find(',')])
            ubl_2_1 += '''
bg-3            <cac:BillingReference>
                <cac:InvoiceDocumentReference>
bt-25                    <cbc:ID>''' + str(bt_25) + '''</cbc:ID>
bt-??                    <cbc:IssueDate>''' + str(self.strftime('%Y-%m-%d')) + '''</cbc:IssueDate>
                </cac:InvoiceDocumentReference>
            </cac:BillingReference>'''
        ubl_2_1 += '''
            <cac:AdditionalDocumentReference>
                <cbc:ID>ICV</cbc:ID>
KSA-16                <cbc:UUID>''' + str(ksa_16) + '''</cbc:UUID>
            </cac:AdditionalDocumentReference>
            <cac:AdditionalDocumentReference>
                <cbc:ID>PIH</cbc:ID>
                <cac:Attachment>
ksa-13                    <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">''' + str(ksa_13) + '''</cbc:EmbeddedDocumentBinaryObject>
                </cac:Attachment>
            </cac:AdditionalDocumentReference>'''
        if not previous_hash:
            ubl_2_1 += '''
            <cac:AdditionalDocumentReference>
                <cbc:ID>QR</cbc:ID>
                <cac:Attachment>
ksa-14-ok                    <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">''' + str(self.l10n_sa_qr_code_str) + '''</cbc:EmbeddedDocumentBinaryObject>
                </cac:Attachment>
            </cac:AdditionalDocumentReference>'''
        if not previous_hash:
            if signature:  # BR-KSA-60
                ubl_2_1 += '''
            <cac:Signature>
KSA-15            <cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>
KSA-15            <cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod>
            </cac:Signature>'''
        ubl_2_1 += '''
bg-5            <cac:AccountingSupplierParty>
              <cac:Party>'''
        ubl_2_1 += '''
                <cac:PartyIdentification>
bt-29                    <cbc:ID schemeID="''' + self.company_id.license + '''">''' + self.company_id.license_no + '''</cbc:ID>
                </cac:PartyIdentification>
                <cac:PostalAddress>
bt-35-OK                    <cbc:StreetName>''' + self.company_id.street + '''</cbc:StreetName>'''
        if self.company_id.street2:
            ubl_2_1 += '''
bt-36-ok                    <cbc:AdditionalStreetName>''' + self.company_id.street2 + '''</cbc:AdditionalStreetName>'''
        if len(str(self.company_id.additional_no)) != 4:
            raise exceptions.ValidationError('Company/Seller Additional Number must be exactly 4 digits')
        if len(str(self.company_id.zip)) != 5:
            raise exceptions.ValidationError('Company/Seller PostalZone/Zip must be exactly 5 digits')
        ubl_2_1 += '''
KSA-17-ok                    <cbc:BuildingNumber>''' + str(self.company_id.building_no) + '''</cbc:BuildingNumber>
KSA-23-ok                    <cbc:PlotIdentification>''' + str(self.company_id.additional_no) + '''</cbc:PlotIdentification>
KSA-3-ok                    <cbc:CitySubdivisionName>''' + self.company_id.district + '''</cbc:CitySubdivisionName>
bt-37-ok                    <cbc:CityName>''' + self.company_id.city + '''</cbc:CityName>
bt-38-ok                    <cbc:PostalZone>''' + str(self.company_id.zip) + '''</cbc:PostalZone>
bt-39-ok                    <cbc:CountrySubentity>''' + self.company_id.state_id.name + '''</cbc:CountrySubentity>
                    <cac:Country>
bt-40-ok                        <cbc:IdentificationCode>''' + self.company_id.country_id.code + '''</cbc:IdentificationCode>
                    </cac:Country>
                </cac:PostalAddress>
                <cac:PartyTaxScheme>
bt-31-OK                  <cbc:CompanyID>''' + bt_31 + '''</cbc:CompanyID>
                    <cac:TaxScheme>
                        <cbc:ID>VAT</cbc:ID>
                    </cac:TaxScheme>
                </cac:PartyTaxScheme>
                <cac:PartyLegalEntity>
bt-27                  <cbc:RegistrationName>''' + self.company_id.name + '''</cbc:RegistrationName>
                </cac:PartyLegalEntity>
              </cac:Party>
            </cac:AccountingSupplierParty>
            <cac:AccountingCustomerParty>
              <cac:Party>
                <cac:PartyIdentification>
bt-46                    <cbc:ID schemeID="''' + self.partner_id.buyer_identification + '''">"''' + self.partner_id.buyer_identification_no + '''"</cbc:ID>
                    </cac:PartyIdentification>'''
        if is_tax_invoice:  # Not applicable for simplified tax invoices and associated credit notes and debit notes
            ubl_2_1 += '''
bg-8                <cac:PostalAddress>
bt-50                    <cbc:StreetName>''' + self.partner_id.street + '''</cbc:StreetName>
bt-51                    <cbc:AdditionalStreetName>''' + self.partner_id.street2 + '''</cbc:AdditionalStreetName>
KSA-18                    <cbc:BuildingNumber>''' + str(self.partner_id.building_no) + '''</cbc:BuildingNumber>'''
            if self.partner_id.additional_no:
                ubl_2_1 += '''
KSA-19                    <cbc:PlotIdentification>''' + str(self.partner_id.additional_no) + '''</cbc:PlotIdentification>'''
            ubl_2_1 += '''
KSA-4                    <cbc:CitySubdivisionName>''' + self.partner_id.district + '''</cbc:CitySubdivisionName>
bt-52                    <cbc:CityName>''' + self.partner_id.city + '''</cbc:CityName>
bt-53                    <cbc:PostalZone>''' + str(self.partner_id.zip) + '''</cbc:PostalZone>
bt-54                    <cbc:CountrySubentity>''' + self.partner_id.state_id.name + '''</cbc:CountrySubentity>
                    <cac:Country>
bt-55                        <cbc:IdentificationCode>''' + self.partner_id.country_id.code + '''</cbc:IdentificationCode>
                    </cac:Country>
                </cac:PostalAddress>
                <cac:PartyTaxScheme>'''
            if self.partner_id.vat and not is_exports_invoice:  # BR-KSA-46
                ubl_2_1 += '''
bt-48-OK                 <cbc:CompanyID>''' + self.partner_id.vat + '''</cbc:CompanyID>'''
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
bt-44                  <cbc:RegistrationName>''' + self.partner_id.name + '''</cbc:RegistrationName>
                </cac:PartyLegalEntity>'''
        if bt_121 in ['VATEX-SA-EDU', 'VATEX-SA-HEA'] and self.partner_id.buyer_identification != 'NAT':  #BR-KSA-49
            message = "As tax exemption reason code is in 'VATEX-SA-EDU', 'VATEX-SA-HEA'"
            message += " then Buyer Identification must be 'NAT'"
            raise exceptions.ValidationError(message)
        ubl_2_1 += '''
              </cac:Party>
            </cac:AccountingCustomerParty>'''
#         if accounting_seller_party:
#             ubl_2_1 += '''
#             <cac:AccountingSellerParty>
#               <cac:Party>
#                 <cac:PartyIdentification>
# bt-29                    <cbc:ID schemeID=""></cbc:ID>
#                 </cac:PartyIdentification>
#               </cac:Party>
#             </cac:AccountingSellerParty>'''
        if delivery:
            ubl_2_1 += '''
            <cac:Delivery>'''
            latest_delivery_date = 1 if not is_tax_invoice and is_summary_invoice else 0
            ksa_5 = self.l10n_sa_delivery_date
            if bt_3 == '388' and ksa_2[:2] == '01' or not is_tax_invoice and is_summary_invoice:
                ubl_2_1 += '''
KSA-5                <cbc:ActualDeliveryDate>''' + str(ksa_5.strftime('%Y-%m-%d')) + '''</cbc:ActualDeliveryDate>'''
            if latest_delivery_date and not_know:
                ksa_24 = self.l10n_sa_delivery_date
                if ksa_24 < ksa_5:
                    raise exceptions.ValidationError('LatestDeliveryDate must be less then or equal to ActualDeliveryDate')
                ubl_2_1 += '''
KSA-24                <cbc:LatestDeliveryDate> ''' + str(ksa_24.strftime('%Y-%m-%d')) + ''' </cbc:LatestDeliveryDate> '''
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
            </cac:Delivery>
            '''
        if is_tax_invoice or bt_3 != '388':
            ubl_2_1 += '''
bg-16            <cac:PaymentMeans>'''
            if is_tax_invoice:
                ubl_2_1 += '''
bt-81                <cbc:PaymentMeansCode>''' + str(bt_81) + '''</cbc:PaymentMeansCode>'''
            if bt_3 != '388':
                ubl_2_1 += '''
KSA-10                <cbc:InstructionNote>''' + str(self.credit_debit_reason) + '''</cbc:InstructionNote>'''
            ubl_2_1 += '''
            </cac:PaymentMeans>'''
        if document_level_allowance_charge:
            bt_96 = float(round(Decimal(str(0)), 2))
            bt_96 = 100 if bt_96 > 100 else (0 if bt_96 < 0 else bt_96)
            ubl_2_1 += '''
bg-20            <cac:AllowanceCharge>
                    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
                    <cbc:AllowanceChargeReason>Discount</cbc:AllowanceChargeReason>
bt-92-OK                <cbc:Amount currencyID="SAR">''' + str(bt_92) + '''</cbc:Amount>
bt-??                <cbc:BaseAmount currencyID="SAR">''' + str(bt_92) + '''</cbc:BaseAmount>
                <cac:TaxCategory>
bt-95                    <cbc:ID>''' + "0" + '''</cbc:ID>
bt-96                    <cbc:Percent>''' + str(bt_96) + '''</cbc:Percent>
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
            bt_151 = invoice_line_id.tax_ids.classified_tax_category if invoice_line_id.tax_ids else "E"
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
bg-25            <cac:InvoiceLine>
bt-126                <cbc:ID>''' + str(invoice_line_id.id) + '''</cbc:ID>
bt-129-OK                <cbc:InvoicedQuantity unitCode="PCE">''' + str(bt_129) + '''</cbc:InvoicedQuantity>
bt-131-OK                <cbc:LineExtensionAmount currencyID="SAR">''' + str(bt_131) + '''</cbc:LineExtensionAmount>'''
            if invoice_line_id.discount: #line_allowance_charge:
                invoice_line_xml += '''
bg-27                <cac:AllowanceCharge>
                    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
                    <cbc:AllowanceChargeReasonCode>95</cbc:AllowanceChargeReasonCode>
                    <cbc:AllowanceChargeReason>Discount</cbc:AllowanceChargeReason>
bt-138-OK                    <cbc:MultiplierFactorNumeric>''' + str(bt_138) + '''</cbc:MultiplierFactorNumeric>
bt_136-OK                    <cbc:Amount currencyID="SAR">''' + str(bt_136) + '''</cbc:Amount>
bt_137-OK                    <cbc:BaseAmount currencyID="SAR">''' + str(bt_137) + '''</cbc:BaseAmount>
                    <cac:TaxCategory>
                        <cbc:ID>S</cbc:ID>
                        <cbc:Percent>15</cbc:Percent>
                        <cac:TaxScheme>
                            <cbc:ID>VAT</cbc:ID>
                        </cac:TaxScheme>
                    </cac:TaxCategory>
                </cac:AllowanceCharge>'''
            ksa_11 = float(round(Decimal(str(bt_131 * bt_152/100)), 2))  #BR-KSA-50
            # ksa_11 = 100 if ksa_11 > 100 else (0 if ksa_11 < 0 else ksa_11)
            ksa_12 = float(round(Decimal(str(bt_131 + ksa_11)), 2))  # BR-KSA-51
            # invoice_line_rounding = float(round(Decimal(str(0)), 2))
            # invoice_line_rounding = 100 if invoice_line_rounding > 100 else (0 if invoice_line_rounding < 0 else invoice_line_rounding)
            invoice_line_xml += '''
                <cac:TaxTotal>'''
            if is_tax_invoice:  #BR-KSA-52 and BR-KSA-53
                invoice_line_xml += '''
KSA-11-ok                    <cbc:TaxAmount currencyID="SAR">''' + str(ksa_11) + '''</cbc:TaxAmount>
KSA-12                    <cbc:RoundingAmount currencyID="SAR">''' + str(ksa_12) + '''</cbc:RoundingAmount>'''
# KSA-??                    <cbc:RoundingAmount currencyID="SAR">''' + str(invoice_line_rounding) + '''</cbc:RoundingAmount>
            invoice_line_xml += '''
                </cac:TaxTotal>
                <cac:Item>
bt-153                    <cbc:Name>''' + str(invoice_line_id.product_id.name) + '''</cbc:Name>'''
            if invoice_line_id.product_id.barcode and invoice_line_id.product_id.code_type:
                invoice_line_xml += '''
                    <cac:StandardItemIdentification>
                       <cbc:ID schemeID="''' + str(invoice_line_id.product_id.code_type) + '''">''' + str(invoice_line_id.product_id.barcode) + '''</cbc:ID>
                    </cac:StandardItemIdentification>'''
            invoice_line_xml += '''
                    <cac:ClassifiedTaxCategory>
bt-151-OK                        <cbc:ID>''' + str(bt_151) + '''</cbc:ID>
bt-152-OK                        <cbc:Percent>''' + str(bt_152) + '''</cbc:Percent>'''
#             if bt_151 != 'O':
#                 invoice_line_xml += '''
# bt-152-OK                        <cbc:Percent>''' + str(bt_152) + '''</cbc:Percent>'''
            invoice_line_xml += '''
                        <cac:TaxScheme>
                            <cbc:ID>VAT</cbc:ID>
                        </cac:TaxScheme>
                    </cac:ClassifiedTaxCategory>
                </cac:Item>
                <cac:Price>
bt-146-OK                    <cbc:PriceAmount currencyID="SAR">''' + str(bt_146) + '''</cbc:PriceAmount>
bt-149-??                    <cbc:BaseQuantity unitCode="PCE">''' + str(bt_149) + '''</cbc:BaseQuantity>
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
bg-23                <cac:TaxSubtotal>
bt-116                    <cbc:TaxableAmount currencyID="SAR">''' + str(bt_116) + '''</cbc:TaxableAmount>
bt-117-OK                    <cbc:TaxAmount currencyID="SAR">''' + str(bt_117) + '''</cbc:TaxAmount>
                    <cac:TaxCategory>
bt-118                        <cbc:ID>''' + str(bt_118) + '''</cbc:ID>'''
            if bt_118 != "O":
                tax_subtotal_xml += '''
bt-119                        <cbc:Percent>''' + str(bt_119) + '''</cbc:Percent>'''
            if bt_118 != "S" and bt_118 in ['E', 'O', 'Z']:
                bt_120 = bg_23_list[bg_23]['bt_120']
                bt_121 = bg_23_list[bg_23]['bt_121']
                tax_subtotal_xml += '''
bt-121-OK                        <cbc:TaxExemptionReasonCode>''' + str(bt_121) + '''</cbc:TaxExemptionReasonCode>
bt-120-OK                        <cbc:TaxExemptionReason>''' + str(bt_120) + '''</cbc:TaxExemptionReason>'''
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
bt-110                <cbc:TaxAmount currencyID="SAR">''' + str(bt_110) + '''</cbc:TaxAmount>'''
        ubl_2_1 += tax_subtotal_xml
        ubl_2_1 += '''
            </cac:TaxTotal>
bg-22            <cac:TaxTotal>
bt-111                <cbc:TaxAmount currencyID="SAR">''' + str(bt_111) + '''</cbc:TaxAmount>
            </cac:TaxTotal>'''
        ubl_2_1 += '''
            <cac:LegalMonetaryTotal>
bt-106-OK                <cbc:LineExtensionAmount currencyID="SAR">''' + str(bt_106) + '''</cbc:LineExtensionAmount>
bt-109-OK                <cbc:TaxExclusiveAmount currencyID="SAR">''' + str(bt_109) + " | " + str(self.amount_untaxed) + '''</cbc:TaxExclusiveAmount>
bt-112-OK                <cbc:TaxInclusiveAmount currencyID="SAR">''' + str(bt_112) + " | " + str(self.amount_total) + '''</cbc:TaxInclusiveAmount>
bt-???                <cbc:ChargeTotalAmount currencyID="SAR">''' + str("0") + '''</cbc:ChargeTotalAmount>'''
        if bt_113:
            ubl_2_1 += '''
bt-113-OK                <cbc:PrepaidAmount currencyID="SAR">''' + str(bt_113) + '''</cbc:PrepaidAmount>'''
        ubl_2_1 += '''
bt-???                <cbc:PayableRoundingAmount currencyID="SAR">''' + str("0") + '''</cbc:PayableRoundingAmount>
bt-115-OK                <cbc:PayableAmount currencyID="SAR">''' + str(bt_115) + " | " + str(self.amount_residual) + '''</cbc:PayableAmount>
            </cac:LegalMonetaryTotal>'''
        ubl_2_1 += invoice_line_xml
        ubl_2_1 += '''
        </Invoice>
        '''
        file_name_specification = str(bt_31) + "_" + self.invoice_date.strftime('%Y%m%d') + "T" + self.invoice_date.strftime('%H%M%SZ') + "_" + str(self.id)
        print(ubl_2_1)
        atts = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'account.move'),
            ('res_field', '=', 'zatca_invoice'),
            ('res_id', 'in', self.ids)
        ])
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
        self.zatca_invoice_name = file_name_specification + ".xml"
        if previous_hash:
            atts = self.env['ir.attachment'].sudo().search([('res_model', '=', 'account.move'),
                                                            ('res_field', '=', 'zatca_hash_invoice'),
                                                            ('res_id', 'in', self.ids)])
            if atts:
                atts.sudo().write({'datas': base64.b64encode(bytes(ubl_2_1, 'utf-8'))})
            else:
                atts.sudo().create([{
                    'name': file_name_specification + ".xml",
                    'res_model': 'account.move',
                    'res_field': 'zatca_hash_invoice',
                    'res_id': self.id,
                    'type': 'binary',
                    'datas': base64.b64encode(bytes(ubl_2_1, 'utf-8')),
                    'mimetype': 'text/xml',
                }])
            self.zatca_hash_invoice_name = file_name_specification + ".xml"
        print(atts)
