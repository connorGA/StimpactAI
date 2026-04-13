import { useState } from 'react';
import PurchaseCreditsDialog from '../PurchaseCreditsDialog';
import { Button } from '@/components/ui/button';

export default function PurchaseCreditsDialogExample() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button onClick={() => setOpen(true)}>Open Purchase Dialog</Button>
      <PurchaseCreditsDialog
        open={open}
        onOpenChange={setOpen}
        onPurchase={(credits) => console.log('Purchased', credits, 'credits')}
      />
    </>
  );
}
