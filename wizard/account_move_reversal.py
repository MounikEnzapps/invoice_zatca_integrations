from odoo import api, fields, models, exceptions
from decimal import Decimal
import uuid


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    # KSA-10
    reason = fields.Char(string='Reason', required=1,
                         help="Reasons as per Article 40 (paragraph 1) of KSA VAT regulations")

    def _prepare_default_reversal(self, move):
        res = super(AccountMoveReversal, self)._prepare_default_reversal(move)
        res['credit_debit_reason'] = self.reason
        return res
