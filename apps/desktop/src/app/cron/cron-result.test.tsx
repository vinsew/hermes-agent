import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type * as HermesApi from '@/hermes'
import { en } from '@/i18n/en'
import type { CronJob } from '@/types/hermes'

import { CronJobDetail } from './index'

vi.mock('@/hermes', async importOriginal => ({
  ...(await importOriginal<typeof HermesApi>()),
  getCronJobRuns: vi.fn(async () => [])
}))
afterEach(cleanup)

describe('script-only cron result', () => {
  it.each([
    ['ok', 'Succeeded'],
    ['error', 'Failed'],
    ['unknown', 'unknown'],
    [null, '—']
  ])('shows last outcome %s separately from its absent conversations', async (status, label) => {
    const job = { id: 'backup', name: 'Backup', state: 'scheduled', enabled: true,
      no_agent: true, script: 'backup.py', last_run_at: '2026-09-10T07:23:27Z',
      last_status: status } as CronJob

    render(<CronJobDetail busy={false} c={en.cron} job={job} onEdit={() => {}} onPauseResume={() => {}} onTrigger={() => {}} />)
    await screen.findByText('No linked conversations')
    expect(screen.getByText('Last run result')).toBeTruthy()
    expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    expect(screen.queryByText('No runs yet')).toBeNull()
  })
})
