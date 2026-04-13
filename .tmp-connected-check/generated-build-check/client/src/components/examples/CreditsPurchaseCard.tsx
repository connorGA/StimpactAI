import CreditsPurchaseCard from '../CreditsPurchaseCard';

export default function CreditsPurchaseCardExample() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl">
      <CreditsPurchaseCard
        credits={5}
        price={5}
        onPurchase={(credits) => console.log('Purchase', credits)}
      />
      <CreditsPurchaseCard
        credits={20}
        price={18}
        bonus={5}
        recommended={true}
        onPurchase={(credits) => console.log('Purchase', credits)}
      />
      <CreditsPurchaseCard
        credits={50}
        price={40}
        bonus={15}
        onPurchase={(credits) => console.log('Purchase', credits)}
      />
    </div>
  );
}
