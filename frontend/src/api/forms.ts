import { get, post } from './client'
import type { BorrowerProfile, LoanRequest } from '../types/forms'

export const getBorrower = () => get<BorrowerProfile>('/forms/borrower')

export const saveBorrower = (data: BorrowerProfile) =>
  post<{ saved: boolean; path: string }>('/forms/borrower', data)

export const getLoan = () => get<LoanRequest>('/forms/loan')

export const saveLoan = (data: LoanRequest) =>
  post<{ saved: boolean; path: string }>('/forms/loan', data)
