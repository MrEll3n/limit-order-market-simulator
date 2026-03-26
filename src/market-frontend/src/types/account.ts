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


