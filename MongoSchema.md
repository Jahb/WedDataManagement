# Collection: Users

## Documents: User

```json
    {
        userID: int,
        credit: int,
        orders: orderID[]
    }
```

## Documents: PaymentBarrier

```json
    {
        orderID: str
        amount: int
    }
```

## Documents: CancelPaymentBarrier

```json
    {
        orderID: str
    }
```

# Collection: Orders

## Documents: Order

```json
    {
        orderID: int,
        userID: userID
        items: itemID[]
        paymentStatus: boolean
    }
```

# Collection: Stock

## Documents: Item

```json
    {
        itemID: int,
        stock: number,
        price: number
    }
```
