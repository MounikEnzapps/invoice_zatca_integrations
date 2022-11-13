from odoo import api, fields, models, exceptions
from decimal import Decimal
import uuid


class AccountDebitNote(models.TransientModel):
    _inherit = "account.debit.note"

    # KSA-10
    reason = fields.Char(string='Reason', required=1,
                         help="Reasons as per Article 40 (paragraph 1) of KSA VAT regulations")

    def _prepare_default_values(self, move):
        res = super(AccountDebitNote, self)._prepare_default_values(move)
        res['credit_debit_reason'] = self.reason
        return res
