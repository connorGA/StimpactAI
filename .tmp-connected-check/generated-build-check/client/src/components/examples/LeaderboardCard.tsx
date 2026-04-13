import LeaderboardCard from '../LeaderboardCard';

export default function LeaderboardCardExample() {
  return (
    <div className="max-w-2xl space-y-4">
      <LeaderboardCard
        id="1"
        rank={1}
        title="Epic Orchestral Battle Theme"
        description="Looking for an intense orchestral piece with dramatic strings and powerful brass"
        votes={142}
        totalVotes={300}
        hasVoteCredits={true}
        onVote={() => console.log('Vote clicked')}
      />
      <LeaderboardCard
        id="2"
        rank={2}
        title="Chill Lo-fi Study Beats"
        description="Relaxing lo-fi hip hop with soft piano and vinyl crackle"
        votes={98}
        totalVotes={300}
        hasVoteCredits={true}
      />
      <LeaderboardCard
        id="3"
        rank={3}
        title="Synthwave Retrowave"
        description="80s inspired synthwave with pulsing basslines"
        votes={67}
        totalVotes={300}
        hasVoteCredits={false}
      />
    </div>
  );
}
