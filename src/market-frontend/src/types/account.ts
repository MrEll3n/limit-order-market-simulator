export type User = {
    email: string;
    userId: string;
    role: string;
};

export type Balance = {
    budget: number;
    postBuyBudget: number;
    products: Record<string, ProductBalance>;
};

export type ProductBalance = {
    balance: number;
    volume: number;
    postSellVolume: number;
};

export type OrderHistoryEntry = {
    id: string;
    timestamp: number;
    side: 'buy' | 'sell';
    price: number;
    quantity: number;
    status: 'open' | 'filled' | 'cancelled';
};
