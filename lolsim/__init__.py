"""League of Legends damage and duel simulator (Kalista first, other marksmen pluggable).

Modules
  stats    stat engine for any champion, level and items; damage math
  runes    rune pages
  enemies  fastest-kill dummies, threat profiles, the enemy's event queue
  kits     champion kits (Kalista); add a Kit subclass for another marksman
  effects  item and rune effects, registered by hook
  fight    fight state and loop: simulate()
"""
