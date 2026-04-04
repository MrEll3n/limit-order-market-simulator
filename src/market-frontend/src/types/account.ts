export type User = {
    email: string;
    userId: string;
    role: string;
};

export type Balance = {
    balance: number;
    portfolioValue: number;
    products: Record<string, ProductBalance>;
};

export type ProductBalance = {
    postSellVolume: number;
    price: number | null;
    value: number | null;
};

export type OrderHistoryEntry = {
    id: string;
    timestamp: number;
    side: 'buy' | 'sell';
    price: number;
    quantity: number;
    status: 'open' | 'filled' | 'cancelled';
};
