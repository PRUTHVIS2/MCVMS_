import { render, screen } from '@testing-library/react'
import App from './App'

test('renders placeholder', () => {
  render(<App />)
  const linkElement = screen.getByText(/MCVMS - Milestone A Placeholder/i)
  expect(linkElement).toBeInTheDocument()
})
