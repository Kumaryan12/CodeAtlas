import { request } from './http';

export interface User {
  name: string;
}
export class Client {
  async login(email: string, remember = false) {
    return request(email);
  }
}
export const normalize = (value: string) => value.trim();
export type UserId = string;
