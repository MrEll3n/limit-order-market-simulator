export type LoginResponseOK = {
    accessToken: string;
    tokenType: string;
    expiresIn: string;
    email: string;
    userId: string;
};

export type LoginResponseError = {
    error: string;
};

export type LoginResponse = LoginResponseOK | LoginResponseError;
