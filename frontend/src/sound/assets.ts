/** Exact user-supplied filenames; originals remain untouched. */
export const soundAssets = {
  attack: 'Attack_Low_war-drum__#1-1793668282761.mp3',
  select: 'Select_a_country_Sof_#3-1793668132463.mp3',
  confirm: 'Confirm_country_choi_#1-1793668213461.mp3',
  dice: 'Heavy_wooden_dice_ro_#1-1793667977040.mp3',
  tie: 'Dice_tie_Neutral_woo_#2-1793668515789.mp3',
  defenderLoss: 'Enemy_loses_soldiers_#4-1793668430006.mp3',
  attackerLoss: '2._Your_soldiers_are_#3-1793668474509.mp3',
  conquer: 'Conquer_a_country_Sh_#4-1793668563611.mp3',
  transfer: 'Transfer_soldiers_So_#1-1793668611702.mp3',
  allocate: 'Allocate_reinforceme_#2-1793668652676.mp3',
  endTurn: 'End_turn_Paper_turnp_#1-1793668726970.mp3',
  npc: 'NPC_Step_Quiet_clock_#4-1793668781417.mp3',
  fast: 'Start_fast-forward_S_#1-1793668839457.mp3',
  pause: 'Pause_Soft_mechanica_#1-1793668868441.mp3',
  campaign: 'Start_new_campaign_S_#3-1793668080452.mp3',
  victory: 'Win_the_game_Full_vi_#2-1793668917760.mp3',
  defeat: 'Lose_the_game_Somber_#1-1793668958052.mp3',
  error: 'Error_Gentle_two-ton_#3-1793669060770.mp3',
} as const;
export type SoundEvent = keyof typeof soundAssets;
/** Byte-identical generated runtime copies avoid '#' URL handling differences. */
export const soundUrl = (event: SoundEvent) => `/assets/sounds/${event}.mp3`;
