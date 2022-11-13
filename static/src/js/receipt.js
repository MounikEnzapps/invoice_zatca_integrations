odoo.define('pos_prescription_creation.receipt', function(require){

    var core = require('web.core');
    var QWeb = core.qweb;
	var gui = require('point_of_sale.gui');
	var screens = require('point_of_sale.screens');
    var Printer = require('point_of_sale.Printer').Printer;
    var rpc = require('web.rpc');

    // For POS Receipt
    screens.ReceiptScreenWidget.include({
        render_receipt: function() {
            if (!this.pos.reloaded_order) {
                return this._super();
            }
            var order = this.pos.get_order();
            this.$('.pos-receipt-container').html(QWeb.render('OrderReceipt', {
                widget: this,
                pos: this.pos,
                order: order,
                receipt: order.export_for_printing(),
                orderlines: order.get_orderlines(),
                paymentlines: order.get_paymentlines(),
                newline: '\\n',
            }));
            this.pos.from_loaded_order = true;
        },
        get_receipt_render_env: function() {
            var order = this.pos.get_order();
            return {
                widget: this,
                pos: this.pos,
                order: order,
                receipt: order.export_for_printing(),
                orderlines: order.get_orderlines(),
                paymentlines: order.get_paymentlines(),
                newline: "\\n",
            };
        },
    });

    // For POS Email send
    screens.PaymentScreenWidget.include({
        send_receipt_to_customer: function(order_server_ids) {
            var order = this.pos.get_order();

            var data = {
                widget: this,
                pos: order.pos,
                order: order,
                receipt: order.export_for_printing(),
                orderlines: order.get_orderlines(),
                paymentlines: order.get_paymentlines(),
                newline: "\\n",
            };

            var receipt = QWeb.render('OrderReceipt', data);
            var printer = new Printer();

            return new Promise(function (resolve, reject) {
                printer.htmlToImg(receipt).then(function(ticket) {
                    rpc.query({
                        model: 'pos.order',
                        method: 'action_receipt_to_customer',
                        args: [order.get_name(), order.get_client(), ticket, order_server_ids],
                    }).then(function() {
                      resolve();
                    }).catch(function () {
                      order.set_to_email(false);
                      reject("There is no internet connection, impossible to send the email.");
                    });
                });
            });
        },
    });

});