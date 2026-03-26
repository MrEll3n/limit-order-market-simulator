export type Order = {
    id: string;
    timestamp: number;
    user: string;
    side: 'buy' | 'sell';
    quantity: number;
    price: number;
};

export type OrderBookEntry = {
    ID: string;
    User: string;
    Quantity: number;
    Price: number;
};

export type OrderBookSnapshot = {
    Bids: OrderBookEntry[];
    Asks: OrderBookEntry[];
    Timestamp: number;
};
