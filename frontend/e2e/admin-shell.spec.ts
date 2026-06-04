import { expect, test } from '@playwright/test'

test.describe('admin shell', () => {
  test('home or admin shows layout copy', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('管理台')).toBeVisible()
  })

  test('admin route loads sidebar', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByText('Agent Factory')).toBeVisible()
  })
})
