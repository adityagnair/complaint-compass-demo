import assert from 'node:assert/strict'
import test from 'node:test'
import { filterCustomersBySegments } from './analytics.js'

const customers = [
  { customer_id: 'A', country: 'India', state: 'Delhi', age_group: '18-24', student_status: 'yes', income_bracket: 'low' },
  { customer_id: 'B', country: 'India', state: 'Karnataka', age_group: '25-34', student_status: 'no', income_bracket: 'mid' },
  { customer_id: 'C', country: 'USA', state: 'Oregon', age_group: '25-34', student_status: 'no', income_bracket: 'high' },
]

test('customer segment filters combine across every requested attribute', () => {
  const result = filterCustomersBySegments(customers, {
    country: 'India', state: 'Delhi', age_group: '18-24', student_status: 'yes', income_bracket: 'low',
  })
  assert.deepEqual(result.map((customer) => customer.customer_id), ['A'])
})

test('empty customer segment filters return every customer', () => {
  assert.deepEqual(filterCustomersBySegments(customers, {}), customers)
})
