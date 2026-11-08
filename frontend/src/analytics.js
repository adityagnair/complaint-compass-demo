export function filterCustomersBySegments(customers, filters) {
  return customers.filter((customer) => Object.entries(filters).every(([key, value]) => !value || customer[key] === value))
}
