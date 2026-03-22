import { render, screen, within } from '@testing-library/react';

import Problem from '../Problem';

describe('Problem', () => {
  it('renders both comparison lists with expected heading text', () => {
    render(<Problem />);

    expect(
      screen.getByRole('heading', {
        name: /Every Agency-OS default is tested, not guessed/i,
      }),
    ).toBeInTheDocument();

    const oldWayCard = screen
      .getByRole('heading', { name: /Building with agents today/i })
      .closest('div');
    expect(oldWayCard).not.toBeNull();
    expect(within(oldWayCard as HTMLElement).getAllByRole('listitem')).toHaveLength(5);

    const newWayCard = screen
      .getByRole('heading', { name: /Building with Zero Human Labs/i })
      .closest('div');
    expect(newWayCard).not.toBeNull();
    expect(within(newWayCard as HTMLElement).getAllByRole('listitem')).toHaveLength(5);
  });
});
