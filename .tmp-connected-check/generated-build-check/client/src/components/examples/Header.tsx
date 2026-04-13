import Header from '../Header';

export default function HeaderExample() {
  return (
    <Header
      voteCredits={25}
      onBuyCredits={() => console.log('Buy credits clicked')}
      isAdmin={true}
    />
  );
}
