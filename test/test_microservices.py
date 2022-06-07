import unittest

import utils as tu


class TestMicroservices(unittest.TestCase):
    def test_stock(self):
        # Test /stock/item/create/<price>
        item: dict = tu.create_item(5)

        self.assertTrue('item_id' in item)

        item_id: str = item['item_id']

        # Test /stock/find/<item_id>
        item: dict = tu.find_item(item_id)
        self.assertEqual(item['price'], 5)
        self.assertEqual(item['stock'], 0)

        # Test /stock/add/<item_id>/<number>
        add_stock_response = tu.add_stock(item_id, 50)

        self.assertTrue(200 <= int(add_stock_response) < 300)

        stock_after_add: int = tu.find_item(item_id)['stock']
        self.assertEqual(stock_after_add, 50)

        # Test /stock/subtract/<item_id>/<number>
        over_subtract_stock_response = tu.subtract_stock(item_id, 200)
        self.assertTrue(tu.status_code_is_failure(
            int(over_subtract_stock_response)))

        subtract_stock_response = tu.subtract_stock(item_id, 15)
        self.assertTrue(tu.status_code_is_success(
            int(subtract_stock_response)))

        stock_after_subtract: int = tu.find_item(item_id)['stock']
        self.assertEqual(stock_after_subtract, 35)

    def test_payment(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertTrue('user_id' in user)

        user_id: str = user['user_id']

        # Test /users/credit/add/<user_id>/<amount>
        add_credit_response = tu.add_credit_to_user(user_id, 15)
        self.assertTrue(tu.status_code_is_success(add_credit_response))

        # add item to the stock service
        item: dict = tu.create_item(5)
        self.assertTrue('item_id' in item)

        item_id: str = item['item_id']

        add_stock_response = tu.add_stock(item_id, 50)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertTrue('order_id' in order)

        order_id: str = order['order_id']

        add_item_response = tu.add_item_to_order(order_id, item_id)
        self.assertTrue(tu.status_code_is_success(add_item_response))

        add_item_response = tu.add_item_to_order(order_id, item_id)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        add_item_response = tu.add_item_to_order(order_id, item_id)
        self.assertTrue(tu.status_code_is_success(add_item_response))

        payment_response = tu.payment_pay(user_id, order_id, 10)
        self.assertTrue(tu.status_code_is_success(payment_response))

        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 5)
        
        payment_response2 = tu.payment_pay(user_id, order_id, 10000)
        self.assertTrue(tu.status_code_is_failure(payment_response2))

    def test_order(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertTrue('user_id' in user)

        user_id: str = user['user_id']

        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertTrue('order_id' in order)

        order_id: str = order['order_id']

        # add item to the stock service
        item1: dict = tu.create_item(5)
        self.assertTrue('item_id' in item1)
        item_id1: str = item1['item_id']
        add_stock_response = tu.add_stock(item_id1, 15)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        # add item to the stock service
        item2: dict = tu.create_item(5)
        self.assertTrue('item_id' in item2)
        item_id2: str = item2['item_id']
        add_stock_response = tu.add_stock(item_id2, 1)
        self.assertTrue(tu.status_code_is_success(add_stock_response))

        add_item_response = tu.add_item_to_order(order_id, item_id1)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        add_item_response = tu.add_item_to_order(order_id, item_id2)
        self.assertTrue(tu.status_code_is_success(add_item_response))
        subtract_stock_response = tu.subtract_stock(item_id2, 1)
        self.assertTrue(tu.status_code_is_success(subtract_stock_response))

        tst = tu.checkout_order(order_id)
        checkout_response = tst.status_code
        self.assertTrue(tu.status_code_is_failure(checkout_response))

        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 15)

        add_stock_response = tu.add_stock(item_id2, 15)
        self.assertTrue(tu.status_code_is_success(int(add_stock_response)))

        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 0)

        checkout_response = tu.checkout_order(order_id).status_code
        self.assertTrue(tu.status_code_is_failure(checkout_response))

        add_credit_response = tu.add_credit_to_user(user_id, 15)
        self.assertTrue(tu.status_code_is_success(int(add_credit_response)))

        credit: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit, 15)

        stock: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock, 15)

        checkout_response = tu.checkout_order(order_id).status_code
        self.assertTrue(tu.status_code_is_success(checkout_response))

        stock_after_subtract: int = tu.find_item(item_id1)['stock']
        self.assertEqual(stock_after_subtract, 14)

        credit: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit, 5)

    def create_item_with_cost_and_stock(self, cost: float, stock: int):
        item: dict = tu.create_item(cost)
        self.assertTrue('item_id' in item)
        item_id: str = item['item_id']
        add_stock_response = tu.add_stock(item_id, stock)
        self.assertTrue(tu.status_code_is_success(add_stock_response))
        return item_id

    def test_insufficient_stock(self):
        user_id: str = tu.create_user()['user_id']
        order_id: str = tu.create_order(user_id)['order_id']

        self.assertTrue(tu.status_code_is_success(int( tu.add_credit_to_user(user_id, 100))))
        
        # create items with stock {15, 0, 15}
        item_id_1 = self.create_item_with_cost_and_stock(5, 15)
        item_id_2 = self.create_item_with_cost_and_stock(5, 0)
        item_id_3 = self.create_item_with_cost_and_stock(5, 15)

        # create shopping cart with quantities {2, 1, 1}
        self.assertTrue(tu.status_code_is_success(tu.add_item_to_order(order_id, item_id_1)))
        self.assertTrue(tu.status_code_is_success(tu.add_item_to_order(order_id, item_id_1)))
        self.assertTrue(tu.status_code_is_success(tu.add_item_to_order(order_id, item_id_2)))
        self.assertTrue(tu.status_code_is_success(tu.add_item_to_order(order_id, item_id_3)))
        
        # checkout should fail because we have insufficient item_2
        tst = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_failure(tst.status_code))

        # verify nothing changed after failed checkout
        self.assertEqual(tu.find_user(user_id)['credit'], 100)
        self.assertEqual(tu.find_item(item_id_1)['stock'], 15)
        self.assertEqual(tu.find_item(item_id_2)['stock'], 0)
        self.assertEqual(tu.find_item(item_id_3)['stock'], 15)

        # update stocks to {1, 10, 15}
        self.assertTrue(tu.status_code_is_success(int(tu.subtract_stock(item_id_1, 14))))
        self.assertTrue(tu.status_code_is_success(int(tu.add_stock(item_id_2, 10))))

        # verify everything again
        self.assertEqual(tu.find_user(user_id)['credit'], 100)
        self.assertEqual(tu.find_item(item_id_1)['stock'], 1)
        self.assertEqual(tu.find_item(item_id_2)['stock'], 10)
        self.assertEqual(tu.find_item(item_id_3)['stock'], 15)

        # checkout should fail because we have insufficient item_1
        tst = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_failure(tst.status_code))

        # verify nothing changed after failed checkout
        self.assertEqual(tu.find_user(user_id)['credit'], 100)
        self.assertEqual(tu.find_item(item_id_1)['stock'], 1)
        self.assertEqual(tu.find_item(item_id_2)['stock'], 10)
        self.assertEqual(tu.find_item(item_id_3)['stock'], 15)

        # update stocks to {5, 10, 15}
        self.assertTrue(tu.status_code_is_success(int(tu.add_stock(item_id_1, 4))))

        # verify everything again
        self.assertEqual(tu.find_user(user_id)['credit'], 100)
        self.assertEqual(tu.find_item(item_id_1)['stock'], 5)
        self.assertEqual(tu.find_item(item_id_2)['stock'], 10)
        self.assertEqual(tu.find_item(item_id_3)['stock'], 15)

        # checkout should succeed because everything is in sufficient quantity
        tst = tu.checkout_order(order_id)
        self.assertTrue(tu.status_code_is_success(tst.status_code))

        self.assertEqual(tu.find_user(user_id)['credit'], 80)
        self.assertEqual(tu.find_item(item_id_1)['stock'], 3)
        self.assertEqual(tu.find_item(item_id_2)['stock'], 9)
        self.assertEqual(tu.find_item(item_id_3)['stock'], 14)

    def test_idempotency(self):
        # Test /payment/pay/<user_id>/<order_id>
        user: dict = tu.create_user()
        self.assertTrue('user_id' in user)

        user_id: str = user['user_id']

        # create order in the order service and add item to the order
        order: dict = tu.create_order(user_id)
        self.assertTrue('order_id' in order)

        order_id: str = order['order_id']

        add_funds_resp = tu.add_credit_to_user(user_id, 1000)
        self.assertTrue(tu.status_code_is_success(add_funds_resp))
        
        payment_resp = tu.payment_pay(user_id, order_id, 25)
        self.assertTrue(tu.status_code_is_success(payment_resp))

        # payment should have taken effect
        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 975)

        payment_resp = tu.payment_pay(user_id, order_id, 25) # repeating the same payment is stopped because of idempotency
        self.assertTrue(tu.status_code_is_success(payment_resp))

        payment_resp = tu.payment_pay(user_id, order_id, 50) # repeating the same payment with diff amount is stopped because of idempotency
        self.assertTrue(tu.status_code_is_failure(payment_resp))

        # only the first payment should have taken effect
        credit_after_payment: int = tu.find_user(user_id)['credit']
        self.assertEqual(credit_after_payment, 975)

if __name__ == '__main__':
    unittest.main()
