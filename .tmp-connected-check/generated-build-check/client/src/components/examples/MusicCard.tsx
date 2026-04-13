import MusicCard from '../MusicCard';

export default function MusicCardExample() {
  return (
    <div className="w-72">
      <MusicCard
        id="1"
        title="Neon Dreams"
        artist="AI Composer"
        thumbnail="https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&h=400&fit=crop"
        audioUrl="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
        duration="3:24"
      />
    </div>
  );
}
