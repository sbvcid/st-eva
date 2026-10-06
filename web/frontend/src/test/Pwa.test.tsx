import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import React from 'react'
import App from '../App'
import { isStandaloneMode } from '../services/pwa'

describe('PWA & Offline Capabilities', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('detects standalone mode correctly', () => {
    expect(isStandaloneMode()).toBe(false)
  })

  it('renders offline warning banner when offline', () => {
    // Simulate offline
    Object.defineProperty(navigator, 'onLine', {
      value: false,
      configurable: true,
    })

    render(<App />)

    // Trigger offline event
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })

    expect(
      screen.getByText(/Offline Mode — App shell cached/i)
    ).toBeInTheDocument()

    // Restore online
    act(() => {
      Object.defineProperty(navigator, 'onLine', {
        value: true,
        configurable: true,
      })
      window.dispatchEvent(new Event('online'))
    })
  })

  it('handles beforeinstallprompt event and displays Install App button', async () => {
    render(<App />)

    const promptEvent = new Event('beforeinstallprompt')
    ;(promptEvent as any).prompt = vi.fn().mockResolvedValue(undefined)
    ;(promptEvent as any).userChoice = Promise.resolve({ outcome: 'accepted' })

    act(() => {
      window.dispatchEvent(promptEvent)
    })

    const installButtons = screen.getAllByRole('button', { name: /install/i })
    expect(installButtons.length).toBeGreaterThan(0)

    // Click install button
    await act(async () => {
      fireEvent.click(installButtons[0])
    })
    expect((promptEvent as any).prompt).toHaveBeenCalled()
  })
})
