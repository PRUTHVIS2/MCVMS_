# test_data/id

- `id_ground_truth.csv`: one row per **person track** in a labelled clip.
  Columns: `clip,start_s,end_s,description,expected,view,light,distance,notes`
  - `description`: how to find the person ("blue shirt, left to right, second person").
  - `expected`: `wearing` (card/lanyard clearly visible at some point) | `not_wearing` (chest clearly visible for a while and there is no card) | `unclear` (card could be hidden, back turned, too far).
  - `view`: front | side | back | mixed. `light`: day | dusk | night | backlit. `distance`: near | mid | far.
- Torso crop dataset for training goes in `dataset/id/{train,val,test}/{id_visible,no_id_visible,unusable}/` (docs/06 s5). Split by **person/clip**, never by frame. Consenting classmates only, with the department's OK; keep everything on your machine.
- Clips worth recording (30 to 90 s each): everyone wearing a card; some without; card flipped; card hidden by a bag strap; card in hand; dark lanyard on dark clothes; walking away from the camera; groups of 3 to 5; day and evening light; near and far.
